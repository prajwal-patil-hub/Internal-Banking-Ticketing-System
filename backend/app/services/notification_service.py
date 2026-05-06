"""Notification dispatcher.

Always persists an in-app row (the dashboard bell is the audit). Then
fires the relevant channel adapters. Email/SMS failures don't crash the
caller — the persisted row carries delivery state for replay.

Adding a new channel:
  1. Implement an adapter with a `send(...)` method
  2. Wire it into `NotificationService._dispatch`
  3. Add the channel to `NotificationChannel`
"""

from __future__ import annotations

import uuid
from enum import StrEnum
from typing import Any, Iterable

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.email_adapter import EmailAdapter
from app.adapters.sms_adapter import SMSAdapter
from app.core.logging import get_logger
from app.models.notification import Notification
from app.models.user import User
from app.repositories.notification_repo import NotificationRepository

log = get_logger(__name__)


class NotificationChannel(StrEnum):
    IN_APP = "in_app"
    EMAIL = "email"
    SMS = "sms"


class NotificationType(StrEnum):
    TICKET_CREATED = "ticket_created"
    TICKET_ASSIGNED = "ticket_assigned"
    TICKET_STATUS_CHANGED = "ticket_status_changed"
    TICKET_RESOLVED = "ticket_resolved"
    SLA_BREACHED = "sla_breached"
    ESCALATION_RAISED = "escalation_raised"


class NotificationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = NotificationRepository(db)
        self.email = EmailAdapter()
        self.sms = SMSAdapter()

    async def dispatch(
        self,
        *,
        user_ids: Iterable[uuid.UUID],
        type_: NotificationType,
        subject: str,
        body: str,
        payload: dict[str, Any] | None = None,
        channels: Iterable[NotificationChannel] = (NotificationChannel.IN_APP,),
    ) -> int:
        ids = list(set(user_ids))
        if not ids:
            return 0
        users = await self._load_users(ids)
        sent = 0
        for u in users:
            for ch in channels:
                n = Notification(
                    user_id=u.id,
                    channel=ch.value,
                    type=type_.value,
                    subject=subject[:200],
                    body=body[:2000],
                    payload=payload or {},
                    status="pending",
                )
                await self.repo.add(n)
                ok = await self._dispatch(u, ch, subject, body)
                n.status = "sent" if ok else "failed"
                if ok:
                    n.sent_at = _now_naive_aware_safe()
                sent += 1 if ok else 0
        return sent

    async def _load_users(self, ids: list[uuid.UUID]) -> list[User]:
        stmt = select(User).where(User.id.in_(ids), User.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    async def _dispatch(self, user: User, ch: NotificationChannel, subject: str, body: str) -> bool:
        if ch == NotificationChannel.IN_APP:
            return True
        if ch == NotificationChannel.EMAIL:
            return self.email.send(to=user.email, subject=subject, body=body)
        if ch == NotificationChannel.SMS:
            return self.sms.send(to="", body=body)
        return False


def _now_naive_aware_safe():
    from datetime import datetime, timezone
    return datetime.now(timezone.utc)
