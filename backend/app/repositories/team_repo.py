from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.team import Team


class TeamRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list(self, *, offset: int, limit: int) -> tuple[list[Team], int]:
        total = (await self.db.execute(select(func.count()).select_from(Team))).scalar_one()
        rows = (
            await self.db.execute(
                select(Team).order_by(Team.name).offset(offset).limit(limit)
            )
        ).scalars().all()
        return list(rows), total

    async def get(self, tid: uuid.UUID) -> Team | None:
        return await self.db.get(Team, tid)

    async def create(self, t: Team) -> Team:
        self.db.add(t)
        await self.db.flush()
        return t
