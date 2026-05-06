"""Token-bucket-style rate limiter backed by Redis INCR + EXPIRE.

We use a fixed-window counter (1 minute) which is simpler than full token
bucket and good enough for credential-stuffing defense and write-volume
guards. Returns (allowed, remaining, reset_in_seconds).
"""

from __future__ import annotations

from dataclasses import dataclass

from redis.asyncio import Redis

from app.core.config import settings

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


@dataclass(slots=True)
class RateLimitDecision:
    allowed: bool
    remaining: int
    reset_seconds: int


async def check(key: str, *, limit: int, window_seconds: int) -> RateLimitDecision:
    """Allow up to `limit` operations per `window_seconds` for the given key."""
    redis = _client()
    pipe = redis.pipeline(transaction=False)
    pipe.incr(key)
    pipe.ttl(key)
    count, ttl = await pipe.execute()

    if ttl < 0:  # key has no TTL yet (just created); set it.
        await redis.expire(key, window_seconds)
        ttl = window_seconds

    allowed = int(count) <= limit
    remaining = max(0, limit - int(count))
    return RateLimitDecision(allowed=allowed, remaining=remaining, reset_seconds=int(ttl))


async def aclose() -> None:
    global _redis
    if _redis is not None:
        await _redis.close()
        _redis = None
