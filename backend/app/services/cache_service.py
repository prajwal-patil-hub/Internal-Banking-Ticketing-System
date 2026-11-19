"""A small, optional cache in front of the dashboard aggregates.

`redis==5.0.8` has been a declared dependency since the first commit and was
imported nowhere. This is what it was for.

**What it caches.** The six dashboard endpoints each run a handful of `COUNT`
and `GROUP BY` queries over the whole ticket table. The frontend holds them at
`staleTime: 30_000` with a matching `refetchInterval`, so the numbers a user
sees are already up to thirty seconds old. A thirty-second TTL therefore costs
nothing in freshness — nobody sees staler data than the client was going to
show them anyway — and it is the longest TTL that is honest.

**The key has to carry the scope, not just the endpoint.** `_org_filter`
returns a per-*user* predicate for anyone in an org unit, because it ORs in
`Ticket.assignee_id == user.id` so a manager still sees work assigned directly
to them. Keying on the endpoint alone would serve one user's counts to another
— a quiet, serious data leak dressed as a performance win. `scope_key` below
is built from the user's actual effective scope, and an unscoped viewer
(super-admin, no org unit) gets the shared `all` key because their query really
is identical to every other unscoped viewer's.

**It is optional, and failure is silent.** If Redis is unreachable, every
helper here behaves as a miss and the endpoint computes the answer as it always
did. A cache that can take the dashboard down when it is unavailable is worse
than no cache; this one can only ever fail to help.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

#: Matches the frontend's `staleTime`/`refetchInterval`. Raising it past that
#: would start showing people data older than the UI leads them to expect.
TTL_SECONDS = 30

_client: Any = None
_unavailable = False


def _redis() -> Any:
    """The shared client, or None if Redis cannot be used.

    Connection failures are latched in `_unavailable` so a down Redis costs one
    failed connect rather than one per request — otherwise the "cache" would
    add latency to every call it fails to serve.
    """
    global _client, _unavailable
    if _unavailable:
        return None
    if _client is not None:
        return _client
    try:
        import redis.asyncio as aioredis

        _client = aioredis.from_url(
            settings.REDIS_URL,
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        return _client
    except Exception as exc:  # pragma: no cover - import or URL problems
        _unavailable = True
        log.warning("cache.unavailable", error=str(exc))
        return None


def reset_for_tests() -> None:
    """Drop the latched client. Tests that patch `settings.REDIS_URL` need this."""
    global _client, _unavailable
    _client = None
    _unavailable = False


def scope_key(user: Any, accessible_unit_ids: set | list | None) -> str:
    """A stable identifier for *the set of tickets this user can count*.

    Two users with the same string here are guaranteed to get the same answer
    from the same aggregate query, which is exactly the condition for sharing a
    cache entry. Anything else gets its own.
    """
    if accessible_unit_ids is None and getattr(user, "is_super_admin", False):
        # No predicate at all: every unscoped viewer runs the identical query.
        return "all"
    if accessible_unit_ids is None:
        role = getattr(getattr(user, "role", None), "name", "none")
        if role == "branch_user":
            return f"reporter:{user.id}"
        return "all"
    # Org users carry `OR assignee_id = me`, so the user is part of the scope.
    units = ",".join(sorted(str(u) for u in accessible_unit_ids))
    digest = hashlib.sha256(units.encode()).hexdigest()[:16]
    return f"units:{digest}:me:{user.id}"


async def get(namespace: str, key: str) -> Any | None:
    """Return the cached value, or None on a miss or any failure."""
    client = _redis()
    if client is None:
        return None
    try:
        raw = await client.get(f"dash:{namespace}:{key}")
    except Exception as exc:
        log.warning("cache.get_failed", namespace=namespace, error=str(exc))
        return None
    if raw is None:
        return None
    try:
        return json.loads(raw)
    except ValueError:
        # A value we cannot parse is a value we did not write. Treat as a miss.
        return None


async def set(namespace: str, key: str, value: Any, ttl: int = TTL_SECONDS) -> None:
    """Store a value. Failures are logged and otherwise ignored."""
    client = _redis()
    if client is None:
        return
    try:
        await client.setex(f"dash:{namespace}:{key}", ttl, json.dumps(value, default=str))
    except Exception as exc:
        log.warning("cache.set_failed", namespace=namespace, error=str(exc))


async def close() -> None:
    """Release the connection pool at shutdown."""
    global _client
    if _client is not None:
        with contextlib.suppress(Exception):  # shutdown is best effort
            await _client.aclose()
        _client = None
