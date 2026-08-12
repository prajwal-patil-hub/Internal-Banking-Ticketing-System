"""Branch management — status model and derived load."""

from __future__ import annotations

import pytest

from app.models.branch import Branch, BranchStatus


def test_status_is_separate_from_is_active() -> None:
    """A degraded branch is still active.

    `is_active` is lifecycle — a decommissioned branch. `status` is service
    state — a branch with a dead ATM is very much active and very much not
    operational, and one boolean cannot say both.
    """
    assert {s.value for s in BranchStatus} == {"operational", "maintenance", "incident"}
    assert hasattr(Branch, "is_active")
    assert hasattr(Branch, "status")


def test_branch_carries_the_operational_fields() -> None:
    for field in ("status", "status_note", "manager_id", "ticket_capacity"):
        assert hasattr(Branch, field), f"Branch is missing {field}"


# ---------------------------------------------------------------------------
# Load calculation
# ---------------------------------------------------------------------------

def _load(open_tickets: int, capacity: int) -> int:
    """Mirror of the expression in `_serialize`."""
    return min(round((open_tickets / capacity) * 100), 100) if capacity else 0


@pytest.mark.parametrize(
    "open_tickets,capacity,expected",
    [(0, 20, 0), (5, 20, 25), (10, 20, 50), (20, 20, 100)],
)
def test_load_is_a_percentage_of_capacity(open_tickets, capacity, expected) -> None:
    assert _load(open_tickets, capacity) == expected


def test_load_is_capped_at_full() -> None:
    """An over-subscribed branch renders as a full bar, not an overflowing one."""
    assert _load(45, 20) == 100


def test_zero_capacity_does_not_divide_by_zero() -> None:
    assert _load(5, 0) == 0


def test_ticket_counts_are_not_stored_on_the_branch() -> None:
    """They must stay derived.

    A denormalised counter means every ticket transition has to remember to
    adjust it, and the first missed update leaves a number that is wrong
    forever with nothing to reveal it.
    """
    assert not hasattr(Branch, "open_tickets")
    assert not hasattr(Branch, "breached_tickets")
