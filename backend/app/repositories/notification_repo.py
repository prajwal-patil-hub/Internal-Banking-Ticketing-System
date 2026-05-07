from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import Notification


class NotificationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, n: Notification) -> Notification:
        self.db.add(n)
        await self.db.flush()
        return n

    async def list_for_user(
        self, user_id: uuid.UUID, *, channel: str | None = None,
        unread_only: bool = False, offset: int = 0, limit: int = 20,
    ) -> tuple[list[Notification], int]:
        base = select(Notification).where(Notification.user_id == user_id)
        count = select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
        if channel:
            base = base.where(Notification.channel == channel)
            count = count.where(Notification.channel == channel)
        if unread_only:
            base = base.where(Notification.read_at.is_(None))
            count = count.where(Notification.read_at.is_(None))
        rows = (
            await self.db.execute(base.order_by(Notification.created_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        total = (await self.db.execute(count)).scalar_one()
        return list(rows), total

    async def mark_read(self, n: Notification) -> None:
        if n.read_at is None:
            n.read_at = datetime.now(timezone.utc)

    async def get(self, nid: uuid.UUID) -> Notification | None:
        return await self.db.get(Notification, nid)

    async def unread_count(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(func.count())
            .select_from(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def mark_all_read(self, user_id: uuid.UUID) -> int:
        stmt = (
            select(Notification)
            .where(Notification.user_id == user_id, Notification.read_at.is_(None))
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        for r in rows:
            r.read_at = now
        return len(rows)
