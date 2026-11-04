"""One definition of "open", shared by everything that counts tickets.

There used to be six, and they disagreed: the dashboard and the SLA worker
excluded ON_HOLD while the ticket list and the AI's workspace digest included
it. The visible symptom was a KPI card reading "Open: 15" that opened a list of
17 — the two on-hold tickets were invisible in the headline but present in the
drill-down, which reads as a broken filter rather than a definition mismatch.
"""

from __future__ import annotations

import pytest

from app.models.ticket import OPEN_STATUS_VALUES, OPEN_STATUSES, TicketStatus


def test_on_hold_counts_as_open() -> None:
    """Paused is not finished. This is the status the six copies disagreed on."""
    assert TicketStatus.ON_HOLD in OPEN_STATUSES


@pytest.mark.parametrize(
    "status",
    [
        TicketStatus.NEW,
        TicketStatus.ACKNOWLEDGED,
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
        TicketStatus.ON_HOLD,
        TicketStatus.ESCALATED,
        TicketStatus.REOPENED,
    ],
)
def test_outstanding_work_is_open(status) -> None:
    assert status in OPEN_STATUSES


@pytest.mark.parametrize("status", [TicketStatus.RESOLVED, TicketStatus.CLOSED])
def test_finished_work_is_not_open(status) -> None:
    assert status not in OPEN_STATUSES


def test_every_status_is_classified() -> None:
    """No status may fall outside both sets, or it would vanish from both views."""
    closed = {TicketStatus.RESOLVED, TicketStatus.CLOSED}
    assert set(OPEN_STATUSES) | closed == set(TicketStatus)
    assert not set(OPEN_STATUSES) & closed


def test_string_form_matches_the_enum_form() -> None:
    """Some queries compare the column value, others the enum member."""
    assert {s.value for s in OPEN_STATUSES} == OPEN_STATUS_VALUES


def test_no_module_redefines_the_set() -> None:
    """Each consumer must import it, not restate it.

    A local copy is how the definitions drifted apart in the first place, and
    the drift is silent — every page still renders, it just renders a different
    number than the page next to it.
    """
    import pathlib

    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        if path.name == "ticket.py" and path.parent.name == "models":
            continue  # the one true home
        text = path.read_text()
        for marker in ("_OPEN_STATUSES = [", "_OPEN_STATUSES = {",
                       "OPEN_STATUSES = [", "open_statuses = ["):
            if marker in text:
                offenders.append(f"{path.relative_to(root)} ({marker.strip()})")

    assert not offenders, "these modules redefine the open-status set: " + ", ".join(offenders)


# ---------------------------------------------------------------------------
# Risk banding — one owner for the threshold
# ---------------------------------------------------------------------------

def test_risk_band_matches_the_filter_thresholds() -> None:
    """The band the API sends must agree with the SQL the list filter runs.

    AIBadge.tsx used to band at 0.7/0.3 while these constants band at 0.7/0.4,
    so a ticket scored 0.35 read "Med Risk" on the badge and came back from
    `?ai_risk=low`. The band is now computed here, from these constants, and
    sent to the client — so there is nothing left to disagree.
    """
    from app.models.ticket import (
        AI_RISK_HIGH_THRESHOLD,
        AI_RISK_MEDIUM_THRESHOLD,
        risk_band,
    )

    assert risk_band(None) is None
    assert risk_band(0.0) == "low"
    # The score that used to contradict itself.
    assert risk_band(0.35) == "low"
    assert risk_band(AI_RISK_MEDIUM_THRESHOLD - 0.001) == "low"
    assert risk_band(AI_RISK_MEDIUM_THRESHOLD) == "medium"
    assert risk_band(AI_RISK_HIGH_THRESHOLD - 0.001) == "medium"
    assert risk_band(AI_RISK_HIGH_THRESHOLD) == "high"
    assert risk_band(1.0) == "high"


def test_serialized_ticket_carries_the_band() -> None:
    """A score without a band would send the client straight back to guessing."""
    import uuid
    from datetime import UTC, datetime

    from app.api.v1.routes.tickets import _serialize_ticket
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

    ticket = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260827-00001",
        title="t",
        description="d",
        status=TicketStatus.NEW,
        priority=TicketPriority.MEDIUM,
        source=TicketSource.PORTAL,
        reporter_id=uuid.uuid4(),
    )
    ticket.created_at = ticket.updated_at = datetime.now(UTC)
    ticket.ai_risk_score = 0.35

    data = _serialize_ticket(ticket)
    assert data["ai_risk_score"] == 0.35
    assert data["ai_risk_band"] == "low"
