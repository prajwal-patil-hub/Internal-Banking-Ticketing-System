"""Escalation service.

Two paths:
  - manual: agent / supervisor fires `WorkflowService.escalate(...)`,
    which transitions status and we mirror that into an Escalation row.
  - automatic: the SLA breach scan calls `raise_for_breach(...)` and
    notifies the supervisor pool.

Both paths funnel through here so reports like "average time to handle
level-1 escalations" stay one query away.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.rbac import Role
from app.models.escalation import Escalation
from app.models.role import Role as RoleModel
from app.models.user import User
from app.repositories.escalation_repo import EscalationRepository
from app.services.notification_service import (
    NotificationChannel,
    NotificationService,
    NotificationType,
)


class EscalationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = EscalationRepository(db)
        self.notifications = NotificationService(db)

    async def _supervisor_user_ids(self) -> list[uuid.UUID]:
        stmt = (
            select(User.id)
            .join(RoleModel, RoleModel.id == User.role_id)
            .where(RoleModel.name == Role.SUPERVISOR.value, User.is_active.is_(True))
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def raise_manual(
        self, *, ticket_id: uuid.UUID, triggered_by: User, reason: str
    ) -> Escalation:
        latest = await self.repo.latest_for(ticket_id)
        level = (latest.level + 1) if (latest and latest.resolved_at is None) else 1
        e = Escalation(
            ticket_id=ticket_id,
            level=level,
            reason=reason[:1000],
            triggered_by_user_id=triggered_by.id,
            is_automatic=False,
        )
        await self.repo.add(e)
        await self.notifications.dispatch(
            user_ids=await self._supervisor_user_ids(),
            type_=NotificationType.ESCALATION_RAISED,
            subject=f"Escalation L{level} raised",
            body=reason or "Manual escalation by an agent.",
            payload={"ticket_id": str(ticket_id), "level": level, "manual": True},
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
        )
        return e

    async def raise_for_breach(self, ticket_id: uuid.UUID) -> Escalation:
        latest = await self.repo.latest_for(ticket_id)
        if latest and latest.resolved_at is None and latest.is_automatic:
            return latest  # idempotent — already escalated for this breach
        e = Escalation(
            ticket_id=ticket_id,
            level=1,
            reason="SLA breach (auto)",
            is_automatic=True,
        )
        await self.repo.add(e)
        await self.notifications.dispatch(
            user_ids=await self._supervisor_user_ids(),
            type_=NotificationType.SLA_BREACHED,
            subject="SLA breach detected",
            body=f"Ticket {ticket_id} has breached its SLA.",
            payload={"ticket_id": str(ticket_id), "level": 1, "manual": False},
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
        )
        return e

    async def resolve(self, *, escalation_id: uuid.UUID) -> Escalation | None:
        from datetime import datetime
        e = await self.repo.get(escalation_id)
        if e is None or e.resolved_at is not None:
            return e
        e.resolved_at = datetime.now(UTC)
        return e
