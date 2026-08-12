"""Per-user rate limiting for expensive endpoints.

Only the AI routes use this. A ticket list costs a few milliseconds of
Postgres; an AI turn occupies the single local model for tens of seconds, so
one user holding the send key can starve everyone else. Ordinary CRUD is left
unlimited deliberately — a limit there would only add failure modes.

Counters live in process memory. That is the right trade for a single-container
deployment and it fails open across a restart, which is preferable to blocking
real work. Running more than one backend replica would need Redis instead; the
interface below is shaped so that swap touches one function.
"""

from __future__ import annotations

import time
from collections import defaultdict, deque

from app.core.exceptions import RateLimitError

#: user id -> timestamps of recent calls, oldest first.
_HITS: dict[str, deque[float]] = defaultdict(deque)

#: Stop unbounded growth from users who never come back.
_MAX_TRACKED_USERS = 10_000


def check_rate_limit(user_id: str, *, limit: int, window_seconds: int = 60) -> None:
    """Record a call and raise once the user is over the limit.

    A sliding window rather than a fixed bucket: a fixed window lets someone
    fire `2 * limit` calls across a boundary, which for an endpoint this
    expensive is the difference between a busy minute and an unusable one.
    """
    if limit <= 0:  # 0 or negative disables the limit
        return

    now = time.monotonic()
    hits = _HITS[user_id]

    cutoff = now - window_seconds
    while hits and hits[0] < cutoff:
        hits.popleft()

    if len(hits) >= limit:
        retry_after = max(1, int(window_seconds - (now - hits[0])))
        raise RateLimitError(
            f"You are sending AI requests too quickly. Try again in {retry_after}s.",
            details={"retry_after_seconds": retry_after, "limit_per_minute": limit},
        )

    hits.append(now)

    if len(_HITS) > _MAX_TRACKED_USERS:
        _evict_idle(cutoff)


def _evict_idle(cutoff: float) -> None:
    for key in [k for k, v in _HITS.items() if not v or v[-1] < cutoff]:
        _HITS.pop(key, None)


def reset_rate_limits() -> None:
    """Clear all counters. For tests."""
    _HITS.clear()
