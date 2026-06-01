"""Shared async Redis client.

Single connection pool per process, lifecycle-managed by the FastAPI app.
Used by rate limiting today; will be reused by SLA scheduler locks, cache,
and feature flags as those land.
"""

from __future__ import annotations

import redis.asyncio as redis

from app.core.config import settings

_client: redis.Redis | None = None


def get_redis() -> redis.Redis:
    """Return the process-wide Redis client.

    Must be initialised via ``init_redis()`` during app startup. Raises if
    accessed before initialisation so we fail loudly rather than silently
    creating a second pool.
    """
    if _client is None:
        raise RuntimeError("Redis client not initialised. Call init_redis() first.")
    return _client


async def init_redis() -> redis.Redis:
    global _client
    if _client is None:
        _client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
            health_check_interval=30,
        )
        # Fail fast on unreachable Redis at boot.
        await _client.ping()
    return _client


async def close_redis() -> None:
    global _client
    if _client is not None:
        await _client.aclose()
        _client = None
