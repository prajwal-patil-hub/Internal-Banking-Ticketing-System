"""Idempotency key support for unsafe POSTs.

Pattern:
  1. Client sends `Idempotency-Key: <uuid>` on a non-idempotent POST.
  2. Server checks Redis for `idem:{actor_id}:{key}`.
       - Hit  -> returns the cached JSON response (HTTP 200).
       - Miss -> reserves the key (NX+EX), runs the handler, caches
                 the success response with a 24 h TTL.
  3. Concurrent retries during the in-flight window get a 409 so the
     client backs off rather than racing.

Limited to a 24 h window (banking-typical retry budget).

This is an opt-in helper used by ticket creation. Other endpoints
remain idempotent by design (PUT/DELETE) or are read-only (GET).
"""

from __future__ import annotations

import json
from typing import Any

from redis.asyncio import Redis

from app.core.config import settings

TTL_SECONDS = 60 * 60 * 24  # 24h
IN_FLIGHT_TTL = 30          # seconds — safety guard against orphaned reservations

_redis: Redis | None = None


def _client() -> Redis:
    global _redis
    if _redis is None:
        _redis = Redis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis


def _key(actor_id: str, key: str) -> str:
    return f"idem:{actor_id}:{key}"


async def lookup(actor_id: str, key: str) -> dict[str, Any] | None:
    raw = await _client().get(_key(actor_id, key))
    if raw is None or raw == "__pending__":
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def reserve(actor_id: str, key: str) -> bool:
    """Atomically reserve a slot — returns True if we got it."""
    got = await _client().set(_key(actor_id, key), "__pending__", ex=IN_FLIGHT_TTL, nx=True)
    return bool(got)


async def is_pending(actor_id: str, key: str) -> bool:
    raw = await _client().get(_key(actor_id, key))
    return raw == "__pending__"


async def store(actor_id: str, key: str, response: dict[str, Any]) -> None:
    await _client().set(_key(actor_id, key), json.dumps(response, default=str), ex=TTL_SECONDS)


async def release(actor_id: str, key: str) -> None:
    """Drop the reservation if the request failed — let the client retry cleanly."""
    redis = _client()
    val = await redis.get(_key(actor_id, key))
    if val == "__pending__":
        await redis.delete(_key(actor_id, key))
