"""Data access for SLA policies and per-ticket tracking."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sla import SLAPolicy, SLATracking
from app.models.ticket import Ticket


class SLAPolicyRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, priority: str) -> SLAPolicy | None:
        stmt = select(SLAPolicy).where(SLAPolicy.priority == priority)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def list(self) -> list[SLAPolicy]:
        return list((await self.db.execute(select(SLAPolicy).order_by(SLAPolicy.priority))).scalars().all())


class SLATrackingRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_ticket(self, ticket_id: uuid.UUID) -> SLATracking | None:
        stmt = select(SLATracking).where(SLATracking.ticket_id == ticket_id)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def add(self, t: SLATracking) -> SLATracking:
        self.db.add(t)
        await self.db.flush()
        return t

    async def find_due_unbreached(self, *, now: datetime, limit: int = 500) -> list[SLATracking]:
        # Tickets that are still in a non-terminal state and whose SLA expired.
        stmt = (
            select(SLATracking)
            .join(Ticket, Ticket.id == SLATracking.ticket_id)
            .where(
                and_(
                    SLATracking.breached.is_(False),
                    SLATracking.paused_at.is_(None),
                    SLATracking.due_at <= now,
                    Ticket.status.notin_(["resolved", "closed"]),
                )
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def find_response_due_unbreached(
        self, *, now: datetime, limit: int = 500
    ) -> list[SLATracking]:
        """Tickets whose response SLA expired without an agent reply yet."""
        stmt = (
            select(SLATracking)
            .join(Ticket, Ticket.id == SLATracking.ticket_id)
            .where(
                and_(
                    SLATracking.response_breached.is_(False),
                    SLATracking.response_due_at.is_not(None),
                    SLATracking.response_due_at <= now,
                    Ticket.first_response_at.is_(None),
                    Ticket.status.notin_(["resolved", "closed"]),
                )
            )
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())

    async def count_breached(self) -> int:
        stmt = select(func.count()).select_from(SLATracking).where(SLATracking.breached.is_(True))
        return (await self.db.execute(stmt)).scalar_one()

    async def count_response_breached(self) -> int:
        stmt = (
            select(func.count())
            .select_from(SLATracking)
            .where(SLATracking.response_breached.is_(True))
        )
        return (await self.db.execute(stmt)).scalar_one()

    async def list_breached(self, *, limit: int = 100) -> list[SLATracking]:
        stmt = (
            select(SLATracking)
            .where(SLATracking.breached.is_(True))
            .order_by(SLATracking.breach_at.desc())
            .limit(limit)
        )
        return list((await self.db.execute(stmt)).scalars().all())
