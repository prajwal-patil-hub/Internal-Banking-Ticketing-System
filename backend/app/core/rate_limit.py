"""Redis-backed rate limiting.

Fixed-window counter, evaluated server-side in a single atomic INCR + EXPIRE.
Cheap (one round-trip per request, O(1) memory per key), well-understood, and
suitable for per-endpoint protection of abuse-prone routes (auth, AI, write
ops). Limits are configured per-endpoint via the ``rate_limit()`` dependency
factory.

If Redis is unreachable the limiter fails *open* — we'd rather serve the
request than take the whole API down behind a transient cache outage. The
miss is logged so monitoring surfaces it.

Headers emitted on every limited request:

* ``X-RateLimit-Limit``      — configured ceiling
* ``X-RateLimit-Remaining``  — requests left in the current window
* ``X-RateLimit-Reset``      — unix epoch seconds when the window rolls over
* ``Retry-After``            — only on 429, seconds until the window rolls
"""

from __future__ import annotations

import time
from typing import Callable, Literal

from fastapi import Depends, Request, Response
from redis.exceptions import RedisError

from app.api.v1.deps import get_current_user
from app.core.exceptions import RateLimitError
from app.core.logging import get_logger
from app.core.redis import get_redis
from app.models.user import User

log = get_logger(__name__)

KeyScope = Literal["ip", "user", "user_or_ip"]


def _client_ip(request: Request) -> str:
    # RequestContextMiddleware already stashes this; fall back for safety.
    ip = getattr(request.state, "client_ip", None)
    if ip:
        return ip
    return request.client.host if request.client else "unknown"


def _bucket_key(scope: KeyScope, name: str, request: Request, user: User | None) -> str:
    if scope == "user" and user is not None:
        ident = f"u:{user.id}"
    elif scope == "user_or_ip" and user is not None:
        ident = f"u:{user.id}"
    else:
        ident = f"ip:{_client_ip(request)}"
    return f"rl:{name}:{ident}"


def rate_limit(
    *,
    name: str,
    times: int,
    seconds: int,
    scope: KeyScope = "ip",
) -> Callable:
    """Build a FastAPI dependency that enforces ``times`` requests per
    ``seconds`` window, keyed by ``scope``.

    ``name`` is a short identifier (e.g. ``"auth_login"``) that becomes part
    of the Redis key — pick something stable per route so changing the limit
    later doesn't reset the prefix.
    """
    if scope == "ip":
        async def _dep(request: Request, response: Response) -> None:
            await _enforce(request, response, user=None, name=name, times=times, seconds=seconds, scope=scope)
        return _dep

    async def _dep_with_user(
        request: Request,
        response: Response,
        user: User = Depends(get_current_user),
    ) -> None:
        await _enforce(request, response, user=user, name=name, times=times, seconds=seconds, scope=scope)

    return _dep_with_user


async def _enforce(
    request: Request,
    response: Response,
    *,
    user: User | None,
    name: str,
    times: int,
    seconds: int,
    scope: KeyScope,
) -> None:
    now = int(time.time())
    window_start = now - (now % seconds)
    reset_at = window_start + seconds
    key = f"{_bucket_key(scope, name, request, user)}:{window_start}"

    try:
        client = get_redis()
        async with client.pipeline(transaction=False) as pipe:
            pipe.incr(key)
            pipe.expire(key, seconds)
            count, _ = await pipe.execute()
    except (RedisError, RuntimeError) as exc:
        log.warning("rate_limit_redis_unavailable", name=name, error=str(exc))
        return  # fail-open

    remaining = max(times - int(count), 0)
    response.headers["X-RateLimit-Limit"] = str(times)
    response.headers["X-RateLimit-Remaining"] = str(remaining)
    response.headers["X-RateLimit-Reset"] = str(reset_at)

    if int(count) > times:
        retry_after = max(reset_at - now, 1)
        log.info(
            "rate_limit_exceeded",
            name=name,
            scope=scope,
            count=int(count),
            limit=times,
            key=key,
        )
        raise RateLimitError(
            f"Rate limit exceeded for '{name}'. Retry in {retry_after}s.",
            details={
                "retry_after_seconds": retry_after,
                "limit": times,
                "remaining": 0,
                "reset_at": reset_at,
                "window_seconds": seconds,
            },
        )
