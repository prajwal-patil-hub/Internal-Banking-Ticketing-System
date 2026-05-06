"""Background scheduler for SLA breach detection.

Runs every 60 seconds. Uses a Redis SET NX lock to ensure only one
instance ticks at a time even when the API is horizontally scaled.
"""

from __future__ import annotations

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from redis.asyncio import Redis

from app.core.config import settings
from app.core.logging import get_logger
from app.db.session import SessionLocal
from app.services.escalation_service import EscalationService
from app.services.sla_engine import SLAEngine

log = get_logger(__name__)

LOCK_KEY = "success-bank:sla:lock"
LOCK_TTL_SECONDS = 50


class SLAScheduler:
    def __init__(self) -> None:
        self._scheduler = AsyncIOScheduler()
        self._redis: Redis | None = None

    async def _tick(self) -> None:
        if self._redis is None:
            self._redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
        got = await self._redis.set(LOCK_KEY, "1", ex=LOCK_TTL_SECONDS, nx=True)
        if not got:
            return  # another instance is running this tick
        try:
            async with SessionLocal() as session:
                engine = SLAEngine(session)
                breached = await engine.detect_breaches()
                if breached:
                    esc = EscalationService(session)
                    for ticket_id in breached:
                        await esc.raise_for_breach(ticket_id)
                    await session.commit()
                    log.info("sla_tick", breached=len(breached))
                else:
                    await session.rollback()
        except Exception:  # noqa: BLE001
            log.exception("sla_tick_failed")

    def start(self) -> None:
        self._scheduler.add_job(self._tick, "interval", seconds=60, id="sla_breach_scan",
                                replace_existing=True, coalesce=True, max_instances=1)
        self._scheduler.start()
        log.info("sla_scheduler_started")

    async def stop(self) -> None:
        self._scheduler.shutdown(wait=False)
        if self._redis is not None:
            await self._redis.close()
        log.info("sla_scheduler_stopped")


scheduler = SLAScheduler()
