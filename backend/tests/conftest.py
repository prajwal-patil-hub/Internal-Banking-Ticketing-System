"""Shared fixtures for the integration test suite.

Tests run against a real Postgres + Redis (the same services dev runs against).
Each test gets a clean schema by recreating the alembic-managed tables in a
session-scoped event loop.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from typing import AsyncIterator

import pytest
import pytest_asyncio

# Default test config — overrideable by env (CI uses different hosts).
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql+asyncpg://success:success_dev_pw@localhost:5432/success_bank_test",
)
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/1")
os.environ.setdefault("JWT_SECRET", "test-secret-needs-to-be-at-least-32-chars")
os.environ.setdefault("AI_ENABLED", "false")
os.environ.setdefault("IMAP_ENABLED", "false")
os.environ.setdefault("NOTIFICATION_EMAIL_ENABLED", "false")

# Make `import app.…` work when running pytest from project root.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import create_async_engine

from app.core.redis import get_redis
from app.core.security import create_access_token, hash_password
from app.db.base import Base
from app.db.session import SessionLocal
from app.main import create_app
from app.models import *  # noqa: F401,F403  (register all mappers)
from app.models.role import Role
from app.models.user import User


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _prepare_database() -> AsyncIterator[None]:
    """Drop+recreate the public schema once per test session.

    Cleaner and faster than alembic upgrade for tests, and avoids the
    test suite drifting from production migrations: a separate test
    `test_migrations.py` covers the migration path itself.
    """
    url = os.environ["DATABASE_URL"]
    admin_db_url = url.rsplit("/", 1)[0] + "/postgres"
    target_db = url.rsplit("/", 1)[1]

    admin_engine = create_async_engine(admin_db_url, isolation_level="AUTOCOMMIT")
    async with admin_engine.connect() as conn:
        await conn.execute(text(f"DROP DATABASE IF EXISTS {target_db}"))
        await conn.execute(text(f"CREATE DATABASE {target_db}"))
    await admin_engine.dispose()

    engine = create_async_engine(url)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await engine.dispose()
    yield


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    app = create_app()
    async with app.router.lifespan_context(app):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
            yield ac


@pytest_asyncio.fixture(autouse=True)
async def _flush_rate_limit_keys() -> AsyncIterator[None]:
    """Ensure each test starts with a clean rate-limit window.

    Uses its own short-lived Redis connection so cleanup runs independently
    of the app's lifespan-managed client (which may already be closed by
    the time fixture teardown runs).
    """
    import redis.asyncio as _redis_aio

    r = _redis_aio.from_url(os.environ["REDIS_URL"], decode_responses=True)
    async for key in r.scan_iter(match="rl:*"):
        await r.delete(key)
    yield
    async for key in r.scan_iter(match="rl:*"):
        await r.delete(key)
    await r.aclose()


@pytest_asyncio.fixture
async def agent_user() -> tuple[User, str]:
    """Create (or return) an agent-role user with a known password,
    plus a fresh access token. Used by tests that need an authenticated session.
    """
    async with SessionLocal() as db:
        role = (await db.execute(select(Role).where(Role.name == "agent"))).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), name="agent", description="Agent")
            db.add(role)
            await db.flush()
        user = (
            await db.execute(select(User).where(User.email == "agent@example.com"))
        ).scalar_one_or_none()
        if user is None:
            user = User(
                id=uuid.uuid4(),
                email="agent@example.com",
                full_name="Test Agent",
                password_hash=hash_password("Agent@1234"),
                role_id=role.id,
                is_active=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
        token, _ = create_access_token(subject=str(user.id), role="agent")
        return user, token


@pytest.fixture
def auth_headers(agent_user) -> dict[str, str]:
    _, token = agent_user
    return {"Authorization": f"Bearer {token}"}
