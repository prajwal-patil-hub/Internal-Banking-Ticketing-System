"""One definition of "open", shared by everything that counts tickets.

There used to be six, and they disagreed: the dashboard and the SLA worker
excluded ON_HOLD while the ticket list and the AI's workspace digest included
it. The visible symptom was a KPI card reading "Open: 15" that opened a list of
17 — the two on-hold tickets were invisible in the headline but present in the
drill-down, which reads as a broken filter rather than a definition mismatch.
"""

from __future__ import annotations

import pytest

from app.models.ticket import OPEN_STATUSES, OPEN_STATUS_VALUES, TicketStatus


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
    assert OPEN_STATUS_VALUES == {s.value for s in OPEN_STATUSES}


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
