"""Branch data access."""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.branch import Branch


class BranchRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, q: str | None, offset: int, limit: int) -> tuple[list[Branch], int]:
        stmt = select(Branch).order_by(Branch.created_at.desc())
        count_stmt = select(func.count()).select_from(Branch)
        if q:
            like = f"%{q.lower()}%"
            stmt = stmt.where(func.lower(Branch.name).like(like) | func.lower(Branch.code).like(like))
            count_stmt = count_stmt.where(func.lower(Branch.name).like(like) | func.lower(Branch.code).like(like))
        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (await self.db.execute(stmt.offset(offset).limit(limit))).scalars().all()
        return list(rows), total

    async def get(self, branch_id: uuid.UUID) -> Branch | None:
        return await self.db.get(Branch, branch_id)

    async def get_by_code(self, code: str) -> Branch | None:
        stmt = select(Branch).where(Branch.code == code)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def create(self, b: Branch) -> Branch:
        self.db.add(b)
        await self.db.flush()
        return b
