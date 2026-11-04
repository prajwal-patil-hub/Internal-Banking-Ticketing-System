"""Run a scheduled job on exactly one replica.

The three schedulers run inside the API process. That is fine on one instance
and wrong the moment there are two: both would poll the mailbox, both would
evaluate SLA breaches, and both would auto-assign the same stale ticket — so
the documented consequence of the design was that the API could not be scaled
horizontally at all.

A PostgreSQL *session-level* advisory lock fixes that without new
infrastructure. It is held by the connection, released the instant that
connection closes, and needs no table, no row, no cleanup job and no expiry
guesswork. If a replica is killed mid-job — SIGKILL, OOM, container eviction —
its connection dies with it and the lock is gone; the next tick simply
succeeds somewhere else.

Two details that are easy to get wrong:

**`pg_try_advisory_lock`, never `pg_advisory_lock`.** The blocking form would
queue every replica behind the holder, and a five-minute job would leave the
others waiting rather than skipping. Skipping is the correct behaviour: the
work is already being done.

**The lock must be taken and released on the same connection.** SQLAlchemy's
pool hands out connections per session, so this uses one explicit connection
for the whole critical section rather than a session that might check a
different connection back out for the release.

The lock key is derived from the job name, so a typo produces a different lock
rather than silently sharing one with another job.
"""

from __future__ import annotations

import hashlib
from collections.abc import Awaitable, Callable
from contextlib import asynccontextmanager
from typing import TypeVar

from sqlalchemy import text

from app.core.logging import get_logger
from app.db.session import engine

log = get_logger(__name__)

T = TypeVar("T")


def lock_key(name: str) -> int:
    """A stable 63-bit key for a job name.

    Postgres advisory locks take a signed 64-bit integer, so the digest is
    truncated to 63 bits to stay positive — a negative key is legal but makes
    `pg_locks` output needlessly confusing to read during an incident.
    """
    digest = hashlib.sha256(name.encode()).digest()
    return int.from_bytes(digest[:8], "big") & 0x7FFFFFFFFFFFFFFF


@asynccontextmanager
async def advisory_lock(name: str):
    """Yield True if this process holds the lock for `name`, else False.

    The caller decides what to do when it is False; every scheduled job here
    simply returns, because another replica is already running it.
    """
    key = lock_key(name)
    connection = await engine.connect()
    acquired = False
    try:
        acquired = bool(
            (
                await connection.execute(
                    text("SELECT pg_try_advisory_lock(:k)"), {"k": key}
                )
            ).scalar()
        )
        yield acquired
    finally:
        if acquired:
            try:
                await connection.execute(
                    text("SELECT pg_advisory_unlock(:k)"), {"k": key}
                )
            except Exception as exc:  # pragma: no cover - connection already gone
                # Not worth raising over: closing the connection below releases
                # a session-level lock anyway. Logged so a pattern of these is
                # visible rather than silent.
                log.warning("job_lock.unlock_failed", job=name, error=str(exc))
        await connection.close()


async def run_locked(name: str, fn: Callable[[], Awaitable[T]]) -> T | None:
    """Run `fn` only if this process wins the lock for `name`.

    Returns the function's result, or None when another replica held it.
    """
    async with advisory_lock(name) as acquired:
        if not acquired:
            log.debug("job_lock.skipped", job=name)
            return None
        return await fn()
