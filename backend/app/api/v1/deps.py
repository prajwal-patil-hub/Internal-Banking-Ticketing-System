"""Shared FastAPI dependencies for v1 API.

Auth dependencies are added in Phase P1; for now we expose the DB session.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_db():
        yield s
