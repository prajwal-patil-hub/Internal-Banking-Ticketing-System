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

    async def list(self, *, offset: int, limit: int) -> tuple[list[Category], int]:
        total = (await self.db.execute(select(func.count()).select_from(Category))).scalar_one()
        rows = (
            await self.db.execute(
                select(Category).order_by(Category.name).offset(offset).limit(limit)
            )
        ).scalars().all()
        return list(rows), total

    async def get(self, cid: uuid.UUID) -> Category | None:
        return await self.db.get(Category, cid)

    async def create(self, c: Category) -> Category:
        self.db.add(c)
        await self.db.flush()
        return c
