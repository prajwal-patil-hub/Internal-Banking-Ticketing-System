"""The dashboard cache, and the one way it could do real harm.

A cache in front of a per-user query is only safe if the key names the data,
not the endpoint. `_org_filter` ORs in `Ticket.assignee_id == user.id` for
anyone in an org unit, so two managers in the same unit run *different*
queries — and a key built from the unit alone would serve one of them the
other's counts.

These tests pin that. The performance tests below it matter less: if the cache
simply never hit, the dashboard would be slower and correct. If the key is
wrong, it is fast and leaking.
"""

from __future__ import annotations

import uuid

import pytest

from app.services import cache_service


class FakeRole:
    def __init__(self, name: str) -> None:
        self.name = name


class FakeUser:
    def __init__(self, *, role: str, super_admin: bool = False, org_unit_id=None) -> None:
        self.id = uuid.uuid4()
        self.role = FakeRole(role)
        self.is_super_admin = super_admin
        self.org_unit_id = org_unit_id


# ---------------------------------------------------------------------------
# Key isolation — the part that matters
# ---------------------------------------------------------------------------

def test_two_managers_in_the_same_unit_do_not_share_a_key() -> None:
    """The scope ORs in `assignee_id = me`, so the key must carry the user."""
    unit = uuid.uuid4()
    a = FakeUser(role="supervisor", org_unit_id=unit)
    b = FakeUser(role="supervisor", org_unit_id=unit)

    assert cache_service.scope_key(a, {unit}) != cache_service.scope_key(b, {unit})


def test_two_branch_users_do_not_share_a_key() -> None:
    """A branch user's scope is `reporter_id = me` and nothing else."""
    a = FakeUser(role="branch_user")
    b = FakeUser(role="branch_user")

    assert cache_service.scope_key(a, None) != cache_service.scope_key(b, None)


def test_different_unit_sets_do_not_share_a_key() -> None:
    a = FakeUser(role="supervisor", org_unit_id=uuid.uuid4())
    assert cache_service.scope_key(a, {uuid.uuid4()}) != cache_service.scope_key(
        a, {uuid.uuid4()}
    )


def test_unscoped_viewers_do_share_a_key() -> None:
    """Super admins run a query with no predicate, so it is the same query.

    This is the case the cache exists for: every unrestricted viewer is asking
    precisely the same question of precisely the same rows.
    """
    a = FakeUser(role="admin", super_admin=True)
    b = FakeUser(role="admin", super_admin=True)

    assert cache_service.scope_key(a, None) == cache_service.scope_key(b, None) == "all"


def test_the_same_user_gets_a_stable_key() -> None:
    """Otherwise the cache would never hit."""
    unit = uuid.uuid4()
    u = FakeUser(role="supervisor", org_unit_id=unit)
    assert cache_service.scope_key(u, {unit}) == cache_service.scope_key(u, {unit})


def test_unit_order_does_not_change_the_key() -> None:
    """`get_accessible_org_unit_ids` gives no ordering guarantee."""
    u = FakeUser(role="supervisor", org_unit_id=uuid.uuid4())
    a, b, c = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    assert cache_service.scope_key(u, [a, b, c]) == cache_service.scope_key(u, [c, a, b])


# ---------------------------------------------------------------------------
# Degradation — a cache that can break the dashboard is worse than none
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_returns_none_when_redis_is_unreachable(monkeypatch) -> None:
    cache_service.reset_for_tests()
    monkeypatch.setattr(
        cache_service.settings, "REDIS_URL", "redis://127.0.0.1:1/0", raising=False
    )
    assert await cache_service.get("kpis", "all") is None
    cache_service.reset_for_tests()


@pytest.mark.asyncio
async def test_set_does_not_raise_when_redis_is_unreachable(monkeypatch) -> None:
    """A failed write must not surface as a 500 on the dashboard."""
    cache_service.reset_for_tests()
    monkeypatch.setattr(
        cache_service.settings, "REDIS_URL", "redis://127.0.0.1:1/0", raising=False
    )
    await cache_service.set("kpis", "all", {"open_tickets": 1})
    cache_service.reset_for_tests()


# ---------------------------------------------------------------------------
# Round trip, against a real Redis when one is configured
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_round_trip() -> None:
    import os

    if not os.getenv("REDIS_URL"):
        pytest.skip("REDIS_URL is not set")

    cache_service.reset_for_tests()
    key = f"test:{uuid.uuid4()}"
    payload = {"open_tickets": 7, "avg_resolution_hours": 3.5}

    assert await cache_service.get("kpis", key) is None
    await cache_service.set("kpis", key, payload, ttl=5)
    assert await cache_service.get("kpis", key) == payload

    await cache_service.close()
    cache_service.reset_for_tests()
