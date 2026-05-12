"""Ticket service — orchestration of create + list with role-scoped reads.

Status/priority validation is centralized here. SLA due-date computation
plugs into the SLA engine in P4; for now we set a sane default from
settings.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ValidationError
from app.core.rbac import Role
from app.models.enums import Priority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from sqlalchemy import select

from app.models.role import Role as RoleModel
from app.repositories.ticket_repo import TicketFilter, TicketRepository
from app.services.audit_service import AuditService
from app.services.notification_service import (
    NotificationChannel,
    NotificationService,
    NotificationType,
)
from app.services.sla_engine import SLAEngine
from app.utils.ticket_number import next_ticket_number


class TicketService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = TicketRepository(db)

    async def create(
        self,
        *,
        actor: User,
        branch_id: uuid.UUID,
        category_id: uuid.UUID,
        title: str,
        description: str,
        priority: str,
    ) -> Ticket:
        try:
            prio = Priority(priority)
        except ValueError as e:
            raise ValidationError("Unknown priority.", details={"priority": priority}) from e

        # Branch-user accounts can only raise tickets for their own branch.
        if actor.role.name == Role.BRANCH_USER.value:
            if actor.branch_id is None or actor.branch_id != branch_id:
                raise ValidationError("Branch user can only raise tickets for their own branch.")

        ticket_no = await next_ticket_number(self.db)

        t = Ticket(
            ticket_no=ticket_no,
            branch_id=branch_id,
            raised_by=actor.id,
            category_id=category_id,
            title=title.strip()[:200],
            description=description.strip(),
            priority=prio.value,
            status=TicketStatus.NEW.value,
        )
        await self.repo.create(t)
        await SLAEngine(self.db).on_ticket_created(t)
        await AuditService(self.db).log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action="ticket.created",
            new_value={
                "ticket_no": t.ticket_no, "branch_id": str(t.branch_id),
                "category_id": str(t.category_id), "priority": t.priority,
                "title": t.title, "status": t.status,
            },
        )
        await self._notify_admins_of_new(t)
        return t

    async def _notify_admins_of_new(self, t: Ticket) -> None:
        # Notify every active admin so the queue stays visible.
        stmt = (
            select(User.id)
            .join(RoleModel, RoleModel.id == User.role_id)
            .where(RoleModel.name == Role.ADMIN.value, User.is_active.is_(True))
        )
        admin_ids = list((await self.db.execute(stmt)).scalars().all())
        if not admin_ids:
            return
        await NotificationService(self.db).dispatch(
            user_ids=admin_ids,
            type_=NotificationType.TICKET_CREATED,
            subject=f"New ticket {t.ticket_no} ({t.priority})",
            body=t.title,
            payload={"ticket_id": str(t.id), "ticket_no": t.ticket_no, "priority": t.priority},
            channels=[NotificationChannel.IN_APP],
        )

    async def list_for(
        self,
        actor: User,
        *,
        f: TicketFilter,
        offset: int,
        limit: int,
        sort: str | None = None,
    ) -> tuple[list[Ticket], int]:
        scoped_branch = actor.branch_id if actor.role.name == Role.BRANCH_USER.value else None
        return await self.repo.list(
            f=f, offset=offset, limit=limit, scoped_branch_id=scoped_branch, sort=sort,
        )

    async def get_for(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self.repo.get(ticket_id)
        if t is None:
            raise NotFoundError("Ticket not found.")
        if actor.role.name == Role.BRANCH_USER.value and t.branch_id != actor.branch_id:
            raise NotFoundError("Ticket not found.")
        return t
