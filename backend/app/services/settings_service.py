"""Read and write the handful of settings an administrator may change at runtime.

Kept deliberately small. A setting belongs here only when an operator will
plausibly retune it without a deploy and the change is worth attributing —
the auto-assign delay qualifies; a database URL does not.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.assignment import (
    AUTO_ASSIGN_DELAY_HOURS,
    AUTO_ASSIGN_DELAY_HOURS_DEFAULT,
    SystemSetting,
)

log = get_logger(__name__)

#: Below this the safety net effectively becomes the old behaviour of assigning
#: on creation, which defeats the point of a supervisor deciding. Above it, a
#: ticket can sit unowned for more than a working week.
MIN_DELAY_HOURS = 0.25
MAX_DELAY_HOURS = 168.0


class SettingsService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_raw(self, key: str) -> str | None:
        row = await self.db.get(SystemSetting, key)
        return row.value if row else None

    async def set_raw(self, key: str, value: str, actor_id: uuid.UUID | None) -> None:
        row = await self.db.get(SystemSetting, key)
        if row is None:
            row = SystemSetting(key=key, value=value, updated_by_id=actor_id)
            self.db.add(row)
        else:
            row.value = value
            row.updated_by_id = actor_id
        await self.db.flush()

    async def get_auto_assign_delay_hours(self) -> float:
        """How long a ticket may sit unassigned before the safety net acts.

        Falls back to the default rather than raising if the row is missing or
        has been corrupted by hand — a bad value in one settings row should
        not stop tickets being assigned at all.
        """
        raw = await self.get_raw(AUTO_ASSIGN_DELAY_HOURS)
        if raw is None:
            return AUTO_ASSIGN_DELAY_HOURS_DEFAULT
        try:
            return _clamp(float(raw))
        except (TypeError, ValueError):
            log.warning("settings.bad_auto_assign_delay", raw=raw)
            return AUTO_ASSIGN_DELAY_HOURS_DEFAULT

    async def set_auto_assign_delay_hours(
        self, hours: float, actor_id: uuid.UUID | None
    ) -> float:
        value = _clamp(float(hours))
        await self.set_raw(AUTO_ASSIGN_DELAY_HOURS, str(value), actor_id)
        log.info("settings.auto_assign_delay_set", hours=value, actor_id=str(actor_id))
        return value


def _clamp(hours: float) -> float:
    return max(MIN_DELAY_HOURS, min(MAX_DELAY_HOURS, hours))
