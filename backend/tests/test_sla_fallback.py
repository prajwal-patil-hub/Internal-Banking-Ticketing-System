"""Unit-level checks on the SLA fallback table.

Full pause/resume integration tests will land alongside the postgres
fixture in P8 once we have a test container in CI.
"""

from __future__ import annotations

import os

os.environ.setdefault("JWT_SECRET", "test_secret_must_be_at_least_32_characters_long")
os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///./test.db")

from app.services.sla_engine import _fallback_minutes


def test_fallback_minutes_ordering() -> None:
    assert _fallback_minutes("critical") < _fallback_minutes("high")
    assert _fallback_minutes("high")     < _fallback_minutes("medium")
    assert _fallback_minutes("medium")   < _fallback_minutes("low")


def test_unknown_priority_falls_back_to_medium() -> None:
    assert _fallback_minutes("unknown") == _fallback_minutes("medium")
