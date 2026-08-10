"""Grounding, prompt discipline and cost controls for the AI assistant.

The bug these guard against: the assistant received a fixed system prompt and
no data at all. Asked about the ticket on screen it could not know, and rather
than saying so it produced a page of generic advice — slow, expensive, and
confidently unmoored from the record.
"""

from __future__ import annotations

import pytest

from app.api.v1.routes.ai_chat import _build_system_prompt, _trim_history
from app.core import ratelimit
from app.core.exceptions import RateLimitError
from app.services.chat_context import _render_screen, _rel_hours, _trim


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def test_prompt_carries_the_context_block() -> None:
    prompt = _build_system_prompt("# CONTEXT\nNumber: TKT-20260809-00001")

    assert "TKT-20260809-00001" in prompt


def test_prompt_without_context_tells_the_model_to_decline() -> None:
    """No data must produce a refusal, not an improvised answer."""
    prompt = _build_system_prompt(None)

    assert "# CONTEXT" in prompt
    assert "cannot see" in prompt.lower()


def test_prompt_forbids_inventing_ticket_facts() -> None:
    prompt = _build_system_prompt("# CONTEXT\n(none)").lower()

    assert "never invent" in prompt
    assert "only from the context" in prompt


def test_prompt_forbids_the_generic_tutorial_failure_mode() -> None:
    """The exact behaviour reported: a how-to essay in place of missing data."""
    prompt = _build_system_prompt("x").lower()

    assert "manually" in prompt
    assert "substitute" in prompt


def test_prompt_sets_a_length_budget() -> None:
    prompt = _build_system_prompt("x").lower()

    assert "120 words" in prompt
    assert "no preamble" in prompt


def test_prompt_keeps_the_banking_guardrails() -> None:
    prompt = _build_system_prompt("x").lower()

    assert "pii" in prompt
    assert "compliance team" in prompt


# ---------------------------------------------------------------------------
# History budget
# ---------------------------------------------------------------------------

def test_history_is_trimmed_to_the_budget() -> None:
    turns = [{"role": "user", "content": "x" * 100} for _ in range(20)]

    kept = _trim_history(turns, budget=500)

    assert 0 < len(kept) < 20
    assert sum(len(t["content"]) for t in kept) <= 500


def test_history_keeps_the_most_recent_turns() -> None:
    """The newest exchange is the one the current question depends on."""
    turns = [{"role": "user", "content": f"msg{i}" + "x" * 100} for i in range(10)]

    kept = _trim_history(turns, budget=400)

    assert kept[-1] is turns[-1]
    assert turns[0] not in kept


def test_history_preserves_chronological_order() -> None:
    turns = [{"role": "user", "content": str(i)} for i in range(5)]

    kept = _trim_history(turns, budget=10_000)

    assert [t["content"] for t in kept] == ["0", "1", "2", "3", "4"]


def test_history_keeps_one_turn_even_when_it_blows_the_budget() -> None:
    """Dropping everything would strip the question being answered."""
    turns = [{"role": "user", "content": "x" * 5000}]

    assert len(_trim_history(turns, budget=10)) == 1


def test_empty_history_stays_empty() -> None:
    assert _trim_history([], budget=1000) == []


# ---------------------------------------------------------------------------
# Context rendering
# ---------------------------------------------------------------------------

def test_trim_collapses_whitespace_and_caps_length() -> None:
    assert _trim("a   b\n\nc", 100) == "a b c"
    assert _trim("x" * 50, 10).endswith("…")
    assert len(_trim("x" * 50, 10)) <= 11


def test_trim_renders_missing_values_as_a_dash() -> None:
    assert _trim(None, 10) == "—"
    assert _trim("", 10) == "—"


def test_relative_hours_reads_naturally_in_both_directions() -> None:
    from datetime import UTC, datetime, timedelta

    now = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)

    assert _rel_hours(now + timedelta(hours=3), now) == "in 3h"
    assert _rel_hours(now - timedelta(hours=4), now) == "4h ago"
    assert _rel_hours(now + timedelta(minutes=20), now) == "in 20m"
    assert _rel_hours(None, now) == "—"


def test_screen_block_names_the_page_and_its_filters() -> None:
    block = _render_screen({
        "route": "/sla",
        "label": "SLA Monitor",
        "details": {"tab": "breached"},
    })

    assert "SLA Monitor" in block
    assert "/sla" in block
    assert "tab: breached" in block


def test_screen_block_is_empty_when_nothing_is_known() -> None:
    assert _render_screen({}) == ""


def test_screen_block_bounds_what_a_client_can_inject() -> None:
    """The page block is client-supplied, so it must not be able to bloat the prompt."""
    block = _render_screen({
        "route": "/x",
        "label": "X",
        "details": {f"key{i}": "v" * 500 for i in range(50)},
    })

    assert block.count("  - ") <= 12
    assert "v" * 200 not in block


# ---------------------------------------------------------------------------
# Rate limiting
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _clean_limits():
    ratelimit.reset_rate_limits()
    yield
    ratelimit.reset_rate_limits()


def test_calls_under_the_limit_pass() -> None:
    for _ in range(5):
        ratelimit.check_rate_limit("user-a", limit=5)


def test_the_call_over_the_limit_is_rejected() -> None:
    for _ in range(5):
        ratelimit.check_rate_limit("user-a", limit=5)

    with pytest.raises(RateLimitError) as exc:
        ratelimit.check_rate_limit("user-a", limit=5)

    assert exc.value.status_code == 429
    assert "retry_after_seconds" in exc.value.details


def test_limits_are_per_user() -> None:
    """One user hammering the model must not lock everyone else out."""
    for _ in range(5):
        ratelimit.check_rate_limit("noisy", limit=5)

    ratelimit.check_rate_limit("quiet", limit=5)  # must not raise


def test_a_zero_limit_disables_the_check() -> None:
    for _ in range(100):
        ratelimit.check_rate_limit("user-a", limit=0)


def test_the_window_slides(monkeypatch) -> None:
    clock = {"t": 1000.0}
    monkeypatch.setattr(ratelimit.time, "monotonic", lambda: clock["t"])

    for _ in range(3):
        ratelimit.check_rate_limit("user-a", limit=3)
    with pytest.raises(RateLimitError):
        ratelimit.check_rate_limit("user-a", limit=3)

    clock["t"] += 61  # the old hits fall out of the window
    ratelimit.check_rate_limit("user-a", limit=3)
