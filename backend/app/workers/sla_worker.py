"""SLA breach detection worker — APScheduler-based SLA monitoring.

Checks for newly breached SLA tickets every 5 minutes and sends
breach notifications to managers via NotificationService.
"""

from __future__ import annotations

from datetime import datetime, timezone

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
                from app.models.ticket import Ticket, TicketStatus

                now = datetime.now(timezone.utc)

                open_statuses = [
                    TicketStatus.NEW,
                    TicketStatus.ACKNOWLEDGED,
                    TicketStatus.ASSIGNED,
                    TicketStatus.IN_PROGRESS,
                    TicketStatus.ESCALATED,
                    TicketStatus.REOPENED,
                ]

                # Find sla_tracking rows whose resolution deadline has passed
                # but have not yet been flagged as breached.
                stmt = (
                    select(SLATracking)
                    .join(Ticket, SLATracking.ticket_id == Ticket.id)
                    .where(
                        and_(
                            Ticket.status.in_(open_statuses),
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

                breached_ticket_ids = []
                for tracking in newly_breached:
                    tracking.is_resolution_breached = True
                    tracking.breach_notified_at = now
                    breached_ticket_ids.append(str(tracking.ticket_id))

                    # Also update the denormalised flag on the ticket itself
                    ticket_result = await db.execute(
                        select(Ticket).where(Ticket.id == tracking.ticket_id)
                    )
                    ticket = ticket_result.scalar_one_or_none()
                    if ticket:
                        ticket.sla_breached = True

                await db.commit()

                log.warning(
                    "sla_breaches_detected",
                    count=len(newly_breached),
                    ticket_ids=breached_ticket_ids,
                )

                # Notify managers — NotificationService will be fully implemented
                # when the notification subsystem is wired up.  The intended call is:
                #
                #   notification_service = NotificationService(db)
                #   for tracking in newly_breached:
                #       await notification_service.notify_sla_breach(
                #           ticket_id=tracking.ticket_id,
                #           manager_emails=settings.manager_email_list,
                #       )
                #
                # For now we log the recipient list.
                if settings.manager_email_list:
                    log.info(
                        "sla_breach_notification_queued",
                        recipients=settings.manager_email_list,
                        ticket_count=len(newly_breached),
                    )
                else:
                    log.warning("sla_breach_no_manager_emails_configured")

            except Exception:  # noqa: BLE001
                log.exception("sla_check_error")
    except Exception:  # noqa: BLE001
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
