"""Rate-limiter exhaustive tests — boundary, headers, scope, fail-open.

These are the most important new tests in this branch: the rate limiter is
the security boundary protecting auth and AI endpoints from abuse.
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_login_blocks_11th_request_per_ip(client):
    # 10 allowed per minute per IP. The 11th must be 429 regardless of
    # whether credentials are right or wrong — the limiter runs *before*
    # auth so it can't be used to oracle valid emails.
    statuses = []
    for _ in range(11):
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything-long-enough"},
        )
        statuses.append(r.status_code)

    assert statuses[:10] == [401] * 10
    assert statuses[10] == 429


@pytest.mark.asyncio
async def test_429_carries_standard_headers(client):
    last = None
    for _ in range(11):
        last = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything-long-enough"},
        )
    assert last is not None and last.status_code == 429
    h = last.headers
    assert "Retry-After" in h and int(h["Retry-After"]) >= 1
    assert h["X-RateLimit-Limit"] == "10"
    assert h["X-RateLimit-Remaining"] == "0"
    assert int(h["X-RateLimit-Reset"]) > 0
    body = last.json()
    assert body["error"]["code"] == "RATE_LIMITED"
    assert body["error"]["details"]["limit"] == 10


@pytest.mark.asyncio
async def test_ticket_create_scope_is_per_user(client, auth_headers):
    # 30/min per user. Verify 30 succeed and 31st is 429, scoped to the
    # authenticated user (not IP — both calls come from the same ASGI host).
    last_status = None
    succeeded = 0
    for i in range(31):
        r = await client.post(
            "/api/v1/tickets",
            headers=auth_headers,
            json={"title": f"burst {i}", "priority": "low"},
        )
        last_status = r.status_code
        if r.status_code == 201:
            succeeded += 1
    assert succeeded == 30
    assert last_status == 429


@pytest.mark.asyncio
async def test_remaining_header_decrements(client):
    # Walk down the budget on /auth/refresh (30/min, per IP) and check
    # remaining counts. /auth/refresh on bad payload returns 401 but still
    # passes the rate limit, so the header should still be present.
    seen = []
    for _ in range(5):
        r = await client.post(
            "/api/v1/auth/refresh", json={"refresh_token": "garbage-token"}
        )
        seen.append(r.headers.get("X-RateLimit-Remaining"))
    # 30 budget, 5 used -> remaining seen are 29, 28, 27, 26, 25
    assert seen == ["29", "28", "27", "26", "25"]


@pytest.mark.asyncio
async def test_fail_open_when_redis_down(client, monkeypatch):
    """If Redis raises, the limiter must NOT block traffic — we'd rather
    serve requests than DoS the API behind a cache outage."""
    from app.core import rate_limit as rl

    real_get_redis = rl.get_redis

    class _Broken:
        def pipeline(self, *a, **kw):
            raise RuntimeError("simulated outage")

    monkeypatch.setattr(rl, "get_redis", lambda: _Broken())

    # With Redis broken, even 50 requests should never see a 429.
    for _ in range(15):
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything-long-enough"},
        )
        assert r.status_code != 429, "limiter must fail open"

    monkeypatch.setattr(rl, "get_redis", real_get_redis)
