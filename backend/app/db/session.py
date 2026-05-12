"""Async SQLAlchemy engine + session factory.

We use a single engine per process. Sessions are short-lived and obtained via
`get_db()` FastAPI dependency.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _engine_kwargs(url: str) -> dict[str, Any]:
    """Pool tuning that only applies to drivers with a real pool.

    SQLite (used as a lightweight fallback for unit tests in CI) forces
    `NullPool` and rejects `pool_size` / `max_overflow`. Detect by URL
    prefix and only pass the kwargs where they're meaningful.
    """
    kwargs: dict[str, Any] = {"echo": False, "future": True}
    if url.startswith("sqlite"):
        return kwargs
    kwargs.update(pool_pre_ping=True, pool_size=10, max_overflow=20)
    return kwargs


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    **_engine_kwargs(settings.DATABASE_URL),
)

SessionLocal = async_sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency yielding a transactional session."""
    async with SessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
