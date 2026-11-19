"""Safety net for tickets nobody has picked up.

Assigning a ticket is a supervisor's decision, so nothing is routed at
creation any more. That leaves a gap: a ticket raised at 2am has its SLA
clock running from the moment it is created, and if it waits until someone
arrives it can breach — and then escalate — without ever having had an owner.

This worker closes only that gap. It assigns tickets that are *still*
unassigned after the configured delay, which an administrator sets. It never
touches a ticket somebody has already assigned, and it never reassigns.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.logging import get_logger
from app.models.ticket import OPEN_STATUS_VALUES as _OPEN_STATUSES
from app.models.ticket import Ticket
from app.services.job_lock import run_locked
from app.services.routing_service import RoutingService
from app.services.settings_service import SettingsService

log = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")

#: Never route more than this in one pass. A backlog after an outage should
#: drain over several minutes rather than in one transaction that locks a large
#: slice of the ticket table.
BATCH_LIMIT = 50


async def assign_stale_unassigned_job() -> None:
    """Scheduler entry point. Runs on exactly one replica.

    The schedulers live inside the API process, so without this every replica
    would run this job on the same tick — duplicate mailbox polls, duplicate
    breach evaluations, the same stale ticket auto-assigned twice. A
    session-level Postgres advisory lock makes the extra replicas skip rather
    than queue, and releases itself if the holder dies.
    """
    await run_locked("assignment_safety_net", _assign_stale_unassigned_job_locked)


async def _assign_stale_unassigned_job_locked() -> None:
    from app.db.session import get_db

    try:
        async for db in get_db():
            try:
                delay_hours = await SettingsService(db).get_auto_assign_delay_hours()
                cutoff = datetime.now(UTC) - timedelta(hours=delay_hours)

                stale = (await db.execute(
                    select(Ticket)
                    .options(selectinload(Ticket.assignee))
                    .where(
                        Ticket.assignee_id.is_(None),
                        Ticket.status.in_(_OPEN_STATUSES),
                        Ticket.created_at < cutoff,
                    )
                    .order_by(Ticket.created_at.asc())
                    .limit(BATCH_LIMIT)
                )).scalars().all()

                if not stale:
                    return

                routing = RoutingService(db)
                assigned, unroutable = 0, 0
                for ticket in stale:
                    assignee, reason = await routing.auto_route_ticket(ticket)
                    if assignee is None:
                        unroutable += 1
                        continue
                    ticket.ai_routing_reason = reason[:500]
                    assigned += 1

                await db.commit()
                log.info(
                    "assignment.safety_net_ran",
                    assigned=assigned,
                    unroutable=unroutable,
                    delay_hours=delay_hours,
                )
                if unroutable:
                    # Worth a distinct warning: it means every agent and
                    # supervisor is on leave or deactivated, and tickets are
                    # now accruing SLA with nobody able to take them.
                    log.warning("assignment.no_one_available", count=unroutable)
            except Exception:
                log.exception("assignment_safety_net_error")
    except Exception:
        log.exception("assignment_safety_net_db_error")


async def setup_assignment_worker(app: object) -> None:  # type: ignore[explicit-override]
    """Register the safety-net job and start the scheduler."""
    if scheduler.running:
        log.warning("assignment_worker_already_running")
        return

    # Every five minutes, matching the SLA checker. The delay itself is what
    # controls how long a ticket waits; polling faster than this would only
    # add load for at most five minutes' more precision.
    scheduler.add_job(
        assign_stale_unassigned_job,
        "interval",
        minutes=5,
        id="assignment_safety_net",
        replace_existing=True,
        misfire_grace_time=60,
        coalesce=True,
    )
    scheduler.start()
    log.info("assignment_worker_started", interval_minutes=5)


async def shutdown_assignment_worker() -> None:
    """Stop the scheduler gracefully during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("assignment_worker_stopped")
