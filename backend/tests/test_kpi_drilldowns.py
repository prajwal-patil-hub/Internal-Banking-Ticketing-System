"""Every KPI card must open a list that reproduces its own number.

A card reading "17 resolved" that opens a list of 7 is worse than a card that
does nothing — it reads as a broken filter. The mismatches that motivated this
were both definition drift rather than arithmetic: the card counted one set of
statuses and its link filtered by another.

These assert the definitions line up. The counts themselves are exercised
live against a seeded database; what is pinned here is the pairing, because
that is what silently rots when a filter is added or a status is introduced.
"""

from __future__ import annotations

from app.models.ticket import (
    AI_RISK_HIGH_THRESHOLD,
    AI_RISK_MEDIUM_THRESHOLD,
    OPEN_STATUS_VALUES,
    TicketStatus,
)


def _closed_values() -> set[str]:
    return {s.value for s in TicketStatus} - OPEN_STATUS_VALUES


def test_status_group_closed_is_exactly_resolved_and_closed() -> None:
    """The "AI-Assisted Resolved" tile counts RESOLVED + CLOSED and links to
    `status_group=closed`. If a new terminal status appears, the tile's count
    and its drill-down must both pick it up — or this fails and says so."""
    assert _closed_values() == {TicketStatus.RESOLVED.value, TicketStatus.CLOSED.value}


def test_open_and_closed_partition_every_status() -> None:
    """No status may fall through both filters and become uncountable."""
    every = {s.value for s in TicketStatus}

    assert OPEN_STATUS_VALUES | _closed_values() == every
    assert not (OPEN_STATUS_VALUES & _closed_values())


def test_a_resolved_ticket_is_not_also_open() -> None:
    """Guards the pairing behind "Open" vs "AI-Assisted Resolved"."""
    assert TicketStatus.RESOLVED.value not in OPEN_STATUS_VALUES
    assert TicketStatus.CLOSED.value not in OPEN_STATUS_VALUES


def test_reopened_returns_to_the_open_set() -> None:
    """Reopening must move a ticket back out of the resolved count, or the two
    tiles would sum to more than the number of tickets that exist."""
    assert TicketStatus.REOPENED.value in OPEN_STATUS_VALUES
    assert TicketStatus.REOPENED.value not in _closed_values()


# ---------------------------------------------------------------------------
# Risk banding — the "High Risk" tile and the ai_risk filter must agree
# ---------------------------------------------------------------------------

def test_both_sides_read_the_threshold_from_one_place() -> None:
    """The tile and the `?ai_risk=high` filter must use the same number.

    Importing the constant into both is what makes that true; this asserts the
    constant is the one they import rather than a literal either could change
    alone.
    """
    from app.api.v1.routes import dashboard, tickets

    assert dashboard.AI_RISK_HIGH_THRESHOLD is AI_RISK_HIGH_THRESHOLD
    assert tickets.AI_RISK_HIGH_THRESHOLD is AI_RISK_HIGH_THRESHOLD
    assert tickets.AI_RISK_MEDIUM_THRESHOLD is AI_RISK_MEDIUM_THRESHOLD


def test_the_bands_are_ordered() -> None:
    assert 0 < AI_RISK_MEDIUM_THRESHOLD < AI_RISK_HIGH_THRESHOLD <= 1


def test_every_score_lands_in_exactly_one_band() -> None:
    """No score may match two bands, or a ticket appears in two drill-downs."""
    bands = {
        "high": lambda s: s >= AI_RISK_HIGH_THRESHOLD,
        "medium": lambda s: AI_RISK_MEDIUM_THRESHOLD <= s < AI_RISK_HIGH_THRESHOLD,
        "low": lambda s: s < AI_RISK_MEDIUM_THRESHOLD,
    }

    for score in (0.0, 0.39, AI_RISK_MEDIUM_THRESHOLD, 0.69, AI_RISK_HIGH_THRESHOLD, 1.0):
        matched = [name for name, pred in bands.items() if pred(score)]
        assert len(matched) == 1, f"score {score} matched {matched}"
