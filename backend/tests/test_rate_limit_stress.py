"""Stress / concurrency test for the rate limiter.

Floods the login endpoint with 100 *concurrent* requests against a 10/min
budget and asserts exactly 10 pass and 90 are 429. If the limiter weren't
atomic this would be flaky (you'd see 11+ passes due to race conditions).
"""

from __future__ import annotations

import asyncio

import pytest


@pytest.mark.asyncio
async def test_concurrent_burst_respects_limit(client):
    async def hit() -> int:
        r = await client.post(
            "/api/v1/auth/login",
            json={"email": "nobody@example.com", "password": "anything-long-enough"},
        )
        return r.status_code

    results = await asyncio.gather(*[hit() for _ in range(100)])
    passed = sum(1 for s in results if s in (200, 401))
    blocked = sum(1 for s in results if s == 429)

    assert passed == 10, f"limiter allowed {passed} (expected exactly 10)"
    assert blocked == 90, f"limiter blocked {blocked} (expected exactly 90)"
