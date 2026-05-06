"""Sanity checks on the ticket-status transition matrix."""

from __future__ import annotations

from app.models.enums import ALLOWED_TRANSITIONS, Priority, TicketStatus


def test_every_status_has_an_entry() -> None:
    for s in TicketStatus:
        assert s in ALLOWED_TRANSITIONS, f"missing transitions entry for {s}"


def test_resolved_can_close_or_reopen() -> None:
    assert TicketStatus.CLOSED in ALLOWED_TRANSITIONS[TicketStatus.RESOLVED]
    assert TicketStatus.REOPENED in ALLOWED_TRANSITIONS[TicketStatus.RESOLVED]


def test_priorities_present() -> None:
    assert {p.value for p in Priority} == {"critical", "high", "medium", "low"}
