"""Verify the transition table is applied uniformly.

Pure unit-style: no DB, no FastAPI app — just the matrix invariant.
"""

from __future__ import annotations

from app.models.enums import ALLOWED_TRANSITIONS, TicketStatus


def test_no_transition_to_same_state() -> None:
    for src, targets in ALLOWED_TRANSITIONS.items():
        assert src not in targets, f"self-transition allowed for {src}"


def test_resolved_terminal_paths() -> None:
    targets = ALLOWED_TRANSITIONS[TicketStatus.RESOLVED]
    assert targets <= {TicketStatus.CLOSED, TicketStatus.REOPENED}


def test_closed_only_reopens() -> None:
    assert ALLOWED_TRANSITIONS[TicketStatus.CLOSED] == {TicketStatus.REOPENED}


def test_new_can_only_acknowledge_or_assign() -> None:
    assert ALLOWED_TRANSITIONS[TicketStatus.NEW] == {TicketStatus.ACKNOWLEDGED, TicketStatus.ASSIGNED}
