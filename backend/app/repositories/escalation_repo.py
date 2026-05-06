from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.escalation import Escalation


class EscalationRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, e: Escalation) -> Escalation:
        self.db.add(e)
        await self.db.flush()
        return e

    async def list(self, *, ticket_id: uuid.UUID | None = None,
                   open_only: bool = False, offset: int = 0, limit: int = 50,
                   ) -> tuple[list[Escalation], int]:
        base = select(Escalation)
        count = select(func.count()).select_from(Escalation)
        if ticket_id:
            base = base.where(Escalation.ticket_id == ticket_id)
            count = count.where(Escalation.ticket_id == ticket_id)
        if open_only:
            base = base.where(Escalation.resolved_at.is_(None))
            count = count.where(Escalation.resolved_at.is_(None))
        rows = (
            await self.db.execute(base.order_by(Escalation.escalated_at.desc()).offset(offset).limit(limit))
        ).scalars().all()
        total = (await self.db.execute(count)).scalar_one()
        return list(rows), total

    async def get(self, eid: uuid.UUID) -> Escalation | None:
        return await self.db.get(Escalation, eid)

    async def latest_for(self, ticket_id: uuid.UUID) -> Escalation | None:
        stmt = (
            select(Escalation)
            .where(Escalation.ticket_id == ticket_id)
            .order_by(Escalation.escalated_at.desc())
            .limit(1)
        )
        return (await self.db.execute(stmt)).scalar_one_or_none()
