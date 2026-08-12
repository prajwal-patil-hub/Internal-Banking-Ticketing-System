"""SLA breach detection worker — APScheduler-based SLA monitoring.

Checks for newly breached SLA tickets every 5 minutes and sends
breach notifications to managers via NotificationService.
"""

from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def check_sla_breaches_job() -> None:
    """Detect newly breached SLA tickets and dispatch notifications.

    Runs every 5 minutes. For each ticket whose resolution deadline has
    passed (and was not already marked breached), marks the ticket,
    updates sla_tracking, and notifies the configured manager addresses.
    """
    from app.db.session import get_db

    try:
        async for db in get_db():
            try:
                from sqlalchemy import and_, select

                from app.models.sla import SLATracking
                from app.models.ticket import OPEN_STATUSES, Ticket

                now = datetime.now(UTC)


                # Find sla_tracking rows whose resolution deadline has passed
                # but have not yet been flagged as breached.
                stmt = (
                    select(SLATracking)
                    .join(Ticket, SLATracking.ticket_id == Ticket.id)
                    .where(
                        and_(
                            Ticket.status.in_(OPEN_STATUSES),
                            SLATracking.is_resolution_breached == False,  # noqa: E712
                            SLATracking.resolution_due_at <= now,
                            SLATracking.paused_at.is_(None),  # don't breach paused timers
                        )
                    )
                )
                result = await db.execute(stmt)
                newly_breached: list[SLATracking] = list(result.scalars().all())

                if not newly_breached:
                    log.debug("sla_check_no_breaches", checked_at=now.isoformat())
                    await db.commit()
                    return

                from app.services.escalation_service import (
                    EscalationService,
                    notify_escalation_outcome,
                )

                escalator = EscalationService(db)
                breached_ticket_ids: list[str] = []
                # (ticket, outcome) pairs to notify once the commit lands.
                pending_notifications = []

                for tracking in newly_breached:
                    tracking.is_resolution_breached = True
                    tracking.breach_notified_at = now
                    breached_ticket_ids.append(str(tracking.ticket_id))

                    # Also update the denormalised flag on the ticket itself
                    ticket_result = await db.execute(
                        select(Ticket).where(Ticket.id == tracking.ticket_id)
                    )
                    ticket = ticket_result.scalar_one_or_none()
                    if not ticket:
                        continue
                    ticket.sla_breached = True

                    # Apply the escalation rules. This is the step that was
                    # missing: the worker marked the breach and stopped, so
                    # rules were never evaluated, no event was ever written,
                    # and escalation depended on somebody noticing the red row.
                    outcome = await escalator.escalate_breached(ticket)
                    if outcome.escalated:
                        pending_notifications.append((ticket, outcome))
                    else:
                        log.debug(
                            "sla_breach_not_escalated",
                            ticket_id=str(ticket.id),
                            reason=outcome.reason,
                        )

                await db.commit()

                log.warning(
                    "sla_breaches_detected",
                    count=len(newly_breached),
                    escalated=len(pending_notifications),
                    ticket_ids=breached_ticket_ids,
                )

                # After the commit: an undelivered email is recoverable, a
                # rolled-back escalation is not.
                for ticket, outcome in pending_notifications:
                    await notify_escalation_outcome(db, ticket, outcome)

                if not settings.manager_email_list:
                    log.warning("sla_breach_no_manager_emails_configured")

            except Exception:
                log.exception("sla_check_error")
    except Exception:
        log.exception("sla_check_db_error")


async def setup_sla_worker(app: object) -> None:  # type: ignore[explicit-override]
    """Register the SLA breach check job and start the scheduler.

    Called during application lifespan startup.
    """
    if scheduler.running:
        log.warning("sla_worker_already_running")
        return

    scheduler.add_job(
        check_sla_breaches_job,
        "interval",
        minutes=5,
        id="sla_check",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.start()
    log.info("sla_worker_started", interval_minutes=5)


async def shutdown_sla_worker() -> None:
    """Stop the SLA scheduler gracefully during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("sla_worker_stopped")
