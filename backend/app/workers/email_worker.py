"""Email polling worker — APScheduler-based IMAP polling.

Polls the configured IMAP mailbox every 2 minutes and converts
inbound emails into tickets via EmailService.

The worker is only started when IMAP_ENABLED=true in settings.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def poll_emails_job() -> None:
    """Poll IMAP mailbox and process inbound emails into tickets.

    Runs every 2 minutes via APScheduler. Acquires its own DB session
    so it is fully independent of the request lifecycle.
    """
    from app.db.session import get_db

    try:
        async for _db in get_db():
            try:
                # Import here to avoid circular imports at module load time.
                # EmailService and InboundEmail will be implemented in a later phase.
                from app.models.email_intake import InboundEmail  # noqa: F401

                log.info("email_poll_started", host=settings.IMAP_HOST, mailbox=settings.IMAP_MAILBOX)

                processed_count = 0

                # EmailService.poll_imap_mailbox() will be wired here once the service
                # is implemented. The scaffolding below shows the intended contract:
                #
                #   email_service = EmailService(db)
                #   processed_count = await email_service.poll_imap_mailbox()
                #   await db.commit()

                log.info("email_poll_completed", processed=processed_count)

            except Exception:
                log.exception("email_poll_error")
    except Exception:
        log.exception("email_poll_db_error")


async def setup_email_worker(app: object) -> None:  # type: ignore[explicit-override]
    """Register the email polling job and start the scheduler.

    Called during application lifespan startup. No-ops when IMAP is disabled.
    """
    if not settings.IMAP_ENABLED:
        log.info("email_worker_disabled", reason="IMAP_ENABLED=false")
        return

    if scheduler.running:
        log.warning("email_worker_already_running")
        return

    scheduler.add_job(
        poll_emails_job,
        "interval",
        minutes=2,
        id="email_poll",
        replace_existing=True,
        misfire_grace_time=30,
        coalesce=True,
    )
    scheduler.start()
    log.info(
        "email_worker_started",
        host=settings.IMAP_HOST,
        mailbox=settings.IMAP_MAILBOX,
        interval_minutes=2,
    )


async def shutdown_email_worker() -> None:
    """Stop the email scheduler gracefully during application shutdown."""
    if scheduler.running:
        scheduler.shutdown(wait=False)
        log.info("email_worker_stopped")
