from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.audit import AuditLog


class AuditRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, a: AuditLog) -> AuditLog:
        self.db.add(a)
        await self.db.flush()
        return a

    async def list(
        self,
        *,
        entity_type: str | None = None,
        entity_id: uuid.UUID | None = None,
        action: str | None = None,
        actor_user_id: uuid.UUID | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[AuditLog], int]:
        clauses = []
        if entity_type:
            clauses.append(AuditLog.entity_type == entity_type)
        if entity_id:
            clauses.append(AuditLog.entity_id == entity_id)
        if action:
            clauses.append(AuditLog.action == action)
        if actor_user_id:
            clauses.append(AuditLog.actor_user_id == actor_user_id)
        if date_from:
            clauses.append(AuditLog.created_at >= date_from)
        if date_to:
            clauses.append(AuditLog.created_at <= date_to)

        base = select(AuditLog).order_by(AuditLog.created_at.desc())
        count = select(func.count()).select_from(AuditLog)
        if clauses:
            base = base.where(and_(*clauses))
            count = count.where(and_(*clauses))

        rows = (await self.db.execute(base.offset(offset).limit(limit))).scalars().all()
        total = (await self.db.execute(count)).scalar_one()
        return list(rows), total
