"""Enrich newly-raised tickets with the model, before anyone opens them.

**The gap this closes.** `AIService.categorize_ticket()` was written, correct,
and covered by four passing tests — and nothing called it. The only
categorisation that ever ran lived inside email intake, so `ai_category`,
`ai_confidence` and `ai_risk_score` were written in exactly one place
(`email_service.py`). A ticket raised through the portal had no category and no
risk score, permanently. The green test suite is why it went unnoticed: it
reported health for code that was unreachable.

It also quietly mislabelled a dashboard metric. "AI Sorted" counts
`ai_category IS NOT NULL`, which — with email the only writer — could only ever
count email tickets. It presented as AI coverage and was structurally a
*channel* number.

**Why a worker rather than the create-ticket request.** The obvious fix is to
call the model when the ticket is created. That would make raising a ticket
wait on `glm4`, with `AI_TIMEOUT_SECONDS` at 180. Raising a ticket is the one
thing a branch user does, and it is currently fast. Enrichment is useful but
never urgent — nobody is reading the ticket in the second after it is filed —
so it belongs off the request path entirely.

The same argument applies to the summary, which is why it is generated here
too. `ai-summarize` used to block a click on a full model round trip; now the
summary is usually already written by the time an agent opens the ticket, and
the endpoint serves it from the column.

**What it will not do.**

* It never overwrites a value that is already set. Email intake writes its own
  category and risk at arrival, and a supervisor may have corrected a category
  by hand — neither should be silently replaced by a later model run.
* It never changes `priority`, `category_id`, `assignee_id` or any field the
  SLA or routing engines read. The model's opinion lands in the `ai_*` columns
  and stays advisory. A mis-categorised ticket must not be able to route itself
  to the wrong desk or restart an SLA clock.
* It writes no audit row. Nothing here is a decision a person took, and this
  project has already been bitten once by an `AI_DECISION` row recording a
  decision no model had made. The `ai_interaction_logs` row that `AIService`
  writes is the correct record for "a model ran".
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import or_, select

from app.core.config import settings
from app.core.logging import get_logger
from app.models.ticket import Ticket
from app.services.job_lock import run_locked

log = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

#: Tickets enriched per pass. Each one costs at least one model call, and the
#: local model serves chat and email intake as well — a backlog should drain
#: over several minutes rather than monopolise it.
BATCH_LIMIT = 10

#: How far back to look. A ticket older than this that is still unenriched was
#: raised while the model was down for a long time; leave it rather than
#: spending the budget re-reading history nobody is waiting on. Operators can
#: widen this once if they want an old backlog filled.
MAX_AGE_DAYS = 7

#: Minutes between passes.
INTERVAL_MINUTES = 2


async def enrich_new_tickets_job() -> None:
    """Scheduler entry point. Runs on exactly one replica.

    The schedulers live inside the API process, so without the advisory lock
    every replica would enrich the same ticket on the same tick — duplicate
    model calls, duplicate interaction-log rows, and a race on the write.
    """
    await run_locked("intake_enrichment", _enrich_new_tickets_locked)


def _needs_enrichment():
    """Rows to consider: anything missing a category or a summary.

    Both conditions, not just the category, because email intake writes a
    category but never a summary — so an email ticket still wants the summary
    half of this pass.
    """
    return or_(Ticket.ai_category.is_(None), Ticket.ai_summary.is_(None))


async def enrich_ticket(db, ticket: Ticket) -> bool:
    """Fill whatever is missing on one ticket. Returns True if anything changed.

    Each half is independent: a model failure on the category must not cost the
    summary, and vice versa. A failure is logged and left for the next pass —
    the row simply stays unenriched, which is the state it was already in.
    """
    from app.services import ticket_ai
    from app.services.ai_service import AIService

    changed = False

    if ticket.ai_category is None:
        try:
            result = await AIService(db).categorize_ticket(
                title=ticket.title,
                description=ticket.description or "",
                source_email=ticket.email_from,
            )
        except Exception:
            log.exception("intake_enrichment.categorize_failed", ticket_id=str(ticket.id))
        else:
            # `categorize_ticket` returns a default-shaped result on failure
            # rather than raising, with confidence 0.0 and a routing_reason
            # that says so. Writing that would mark the ticket enriched and
            # stop it ever being retried, so a zero-confidence result is
            # treated as "not done yet".
            if result.confidence > 0:
                ticket.ai_category = result.category
                ticket.ai_subcategory = result.subcategory
                ticket.ai_confidence = result.confidence
                ticket.ai_risk_score = result.risk_score
                ticket.ai_routing_reason = (result.routing_reason or "")[:500] or None
                ticket.ai_sentiment = result.sentiment
                changed = True
            else:
                log.warning(
                    "intake_enrichment.categorize_low_confidence",
                    ticket_id=str(ticket.id),
                )

    if ticket.ai_summary is None:
        try:
            outcome = await ticket_ai.summarise_ticket(ticket, list(ticket.comments or []))
        except Exception:
            log.exception("intake_enrichment.summarise_failed", ticket_id=str(ticket.id))
        else:
            if outcome.ok and outcome.text:
                ticket.ai_summary = outcome.text
                changed = True
            else:
                log.warning(
                    "intake_enrichment.summarise_failed",
                    ticket_id=str(ticket.id),
                    error=outcome.error,
                )

    return changed


async def _enrich_new_tickets_locked() -> None:
    if not settings.AI_ENABLED:
        return

    from app.db.session import get_db

    try:
        async for db in get_db():
            try:
                cutoff = datetime.now(UTC) - timedelta(days=MAX_AGE_DAYS)
                pending = (await db.execute(
                    select(Ticket)
                    .where(_needs_enrichment(), Ticket.created_at >= cutoff)
                    .order_by(Ticket.created_at.desc())
                    .limit(BATCH_LIMIT)
                )).scalars().all()

                if not pending:
                    return

                enriched = 0
                for ticket in pending:
                    if await enrich_ticket(db, ticket):
                        enriched += 1

                await db.commit()
                log.info(
                    "intake_enrichment.pass_complete",
                    considered=len(pending),
                    enriched=enriched,
                )
            except Exception:
                log.exception("intake_enrichment_error")
    except Exception:
        log.exception("intake_enrichment_db_error")


async def setup_enrichment_worker(app: object) -> None:  # type: ignore[explicit-override]
    """Register the enrichment job and start the scheduler."""
    if not settings.AI_ENABLED:
        log.info("enrichment_worker_disabled", reason="AI_ENABLED is false")
        return

    if scheduler.running:
        log.warning("enrichment_worker_already_running")
        return

    # Two minutes, not five. This is the only worker a *person* is waiting on
    # — the value of the summary is that it is there when the agent opens the
    # ticket — while the other two are housekeeping.
    scheduler.add_job(
        enrich_new_tickets_job,
        "interval",
        minutes=INTERVAL_MINUTES,
        id="intake_enrichment",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.start()
    log.info("enrichment_worker_started", interval_minutes=INTERVAL_MINUTES)


async def shutdown_enrichment_worker() -> None:
    """Stop the scheduler gracefully during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("enrichment_worker_stopped")
