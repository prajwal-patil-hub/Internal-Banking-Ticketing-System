from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


class CategoryRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_active(self) -> list[Category]:
        stmt = select(Category).where(Category.is_active.is_(True)).order_by(Category.name)
        return list((await self.db.execute(stmt)).scalars().all())

    async def list(
        self, *, offset: int, limit: int, include_inactive: bool = False,
    ) -> tuple[list[Category], int]:
        stmt = select(Category).order_by(Category.name)
        count_stmt = select(func.count()).select_from(Category)
        if not include_inactive:
            stmt = stmt.where(Category.is_active.is_(True))
            count_stmt = count_stmt.where(Category.is_active.is_(True))
        total = (await self.db.execute(count_stmt)).scalar_one()
        rows = (await self.db.execute(stmt.offset(offset).limit(limit))).scalars().all()
        return list(rows), total

    async def get(self, cid: uuid.UUID) -> Category | None:
        return await self.db.get(Category, cid)

    async def create(self, c: Category) -> Category:
        self.db.add(c)
        await self.db.flush()
        return c
