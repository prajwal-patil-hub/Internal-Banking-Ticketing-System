"""Ticket service — orchestration of create + list with role-scoped reads.

Status/priority validation is centralized here. SLA due-date computation
plugs into the SLA engine in P4; for now we set a sane default from
settings.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.rbac import Role
from app.models.enums import Priority, TicketStatus
from app.models.ticket import Ticket
from app.models.user import User
from app.repositories.ticket_repo import TicketFilter, TicketRepository
from app.utils.ticket_number import next_ticket_number


def _sla_minutes_for(priority: Priority) -> int:
    return {
        Priority.CRITICAL: settings.SLA_CRITICAL_MINUTES,
        Priority.HIGH:     settings.SLA_HIGH_MINUTES,
        Priority.MEDIUM:   settings.SLA_MEDIUM_MINUTES,
        Priority.LOW:      settings.SLA_LOW_MINUTES,
    }[priority]


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
        sla_due_at = datetime.now(timezone.utc) + timedelta(minutes=_sla_minutes_for(prio))

        t = Ticket(
            ticket_no=ticket_no,
            branch_id=branch_id,
            raised_by=actor.id,
            category_id=category_id,
            title=title.strip()[:200],
            description=description.strip(),
            priority=prio.value,
            status=TicketStatus.NEW.value,
            sla_due_at=sla_due_at,
        )
        return await self.repo.create(t)

    async def list_for(
        self,
        actor: User,
        *,
        f: TicketFilter,
        offset: int,
        limit: int,
    ) -> tuple[list[Ticket], int]:
        scoped_branch = actor.branch_id if actor.role.name == Role.BRANCH_USER.value else None
        return await self.repo.list(f=f, offset=offset, limit=limit, scoped_branch_id=scoped_branch)

    async def get_for(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self.repo.get(ticket_id)
        if t is None:
            raise NotFoundError("Ticket not found.")
        if actor.role.name == Role.BRANCH_USER.value and t.branch_id != actor.branch_id:
            raise NotFoundError("Ticket not found.")
        return t
