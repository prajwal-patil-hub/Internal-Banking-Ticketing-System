"""Shared fixtures.

Until now every test mocked the database. That is fine for pure logic, but it
cannot catch a query that is wrong — which is how `inbound_emails` drifted
eleven columns from its model without a single test noticing. `db_session`
gives tests a real Postgres session so a SQL expression can be checked by
running it.

Each test runs inside a transaction that is rolled back afterwards, so the
tests leave the database exactly as they found it and can run against the same
database the migrations were applied to.
"""

from __future__ import annotations

import os

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

DATABASE_URL = os.getenv("DATABASE_URL")


@pytest_asyncio.fixture
async def db_session() -> AsyncSession:
    """A session in a transaction that is always rolled back.

    Skips only when DATABASE_URL is unset — never on a connection failure. A
    fixture that skips when it cannot connect reports "passed" for a suite
    that never ran, which is the same false negative the CI drift gate was
    fixed to avoid. CI always sets DATABASE_URL, so these tests run there.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not set; database-backed tests need one.")

    engine = create_async_engine(DATABASE_URL, poolclass=None)
    connection = await engine.connect()
    transaction = await connection.begin()
    session = async_sessionmaker(bind=connection, expire_on_commit=False)()
    try:
        yield session
    finally:
        await session.close()
        await transaction.rollback()
        await connection.close()
        await engine.dispose()


@pytest_asyncio.fixture
async def committing_session() -> AsyncSession:
    """A session that really commits, for code that rolls back internally.

    `db_session` wraps every test in an outer transaction it rolls back at the
    end. That is the right default, but it cannot be used to test a service
    that calls `rollback()` itself — the service's rollback unwinds the
    fixture's transaction too, taking the test's own fixtures with it and
    leaving detached objects behind.

    So this one commits for real and cleans up afterwards by deleting the
    knowledge-base collections created during the test, which cascades to
    documents, versions and chunks. Slower and less isolated; used only where
    the rollback behaviour *is* the thing under test.
    """
    if not DATABASE_URL:
        pytest.skip("DATABASE_URL is not set; database-backed tests need one.")

    engine = create_async_engine(DATABASE_URL, poolclass=None)
    session = async_sessionmaker(engine, expire_on_commit=False)()

    from sqlalchemy import delete, select

    from app.models.knowledge import KBCollection

    before = set((await session.execute(select(KBCollection.id))).scalars().all())
    try:
        yield session
    finally:
        try:
            await session.rollback()
            after = set((await session.execute(select(KBCollection.id))).scalars().all())
            new = after - before
            if new:
                await session.execute(delete(KBCollection).where(KBCollection.id.in_(new)))
                await session.commit()
        finally:
            await session.close()
            await engine.dispose()
