"""Email polling worker — APScheduler-based IMAP polling.

Polls the configured IMAP mailbox every 2 minutes and converts
inbound emails into tickets via EmailService.

The worker is only started when IMAP_ENABLED=true in settings.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.core.config import settings
from app.core.logging import get_logger
from app.services.job_lock import run_locked

log = get_logger(__name__)

scheduler = AsyncIOScheduler(timezone="UTC")


async def poll_emails_job() -> None:
    """Scheduler entry point. Runs on exactly one replica.

    The schedulers live inside the API process, so without this every replica
    would run this job on the same tick — duplicate mailbox polls, duplicate
    breach evaluations, the same stale ticket auto-assigned twice. A
    session-level Postgres advisory lock makes the extra replicas skip rather
    than queue, and releases itself if the holder dies.
    """
    await run_locked("email_poll", _poll_emails_job_locked)


async def _poll_emails_job_locked() -> None:
    """Poll IMAP mailbox and process inbound emails into tickets.

    Runs every 2 minutes via APScheduler. Acquires its own DB session
    so it is fully independent of the request lifecycle.
    """
    from app.db.session import get_db

    try:
        async for _db in get_db():
            try:
                # Imported here to avoid a circular import at module load time.
                from app.services.email_service import EmailService

                log.info("email_poll_started", host=settings.IMAP_HOST, mailbox=settings.IMAP_MAILBOX)

                # EmailService was fully implemented but nothing ever called
                # it, so the mailbox was never read and every "Via Email"
                # ticket came from the seed. Same shape as the SLA worker,
                # which marked breaches and stopped short of escalating.
                processed_count = await EmailService(_db).poll_imap_mailbox()
                await _db.commit()

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
