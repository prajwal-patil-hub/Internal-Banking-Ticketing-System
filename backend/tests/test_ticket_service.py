"""TicketService unit tests — mocked DB session."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.flush = AsyncMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.add = MagicMock()
    db.get = AsyncMock()
    return db


def _make_ticket(**kwargs):
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

    t = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260513-00001",
        title="Test ticket",
        description="Description here",
        status=TicketStatus.NEW,        # use enum value directly
        priority=TicketPriority.MEDIUM,
        source=TicketSource.PORTAL,
        reporter_id=uuid.uuid4(),
    )
    for k, v in kwargs.items():
        setattr(t, k, v)
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    return t


# ---------------------------------------------------------------------------
# FSM validation
# ---------------------------------------------------------------------------

def test_valid_transitions_mapping() -> None:
    """All 9 statuses have entries in the FSM table."""
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    for status in TicketStatus:
        assert status in VALID_TRANSITIONS, f"Missing FSM entry for {status}"


def test_new_ticket_can_transition_to_acknowledged() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.ACKNOWLEDGED in VALID_TRANSITIONS[TicketStatus.NEW]


def test_new_ticket_cannot_transition_to_resolved() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.RESOLVED not in VALID_TRANSITIONS[TicketStatus.NEW]


def test_resolved_ticket_can_reopen() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.REOPENED in VALID_TRANSITIONS[TicketStatus.RESOLVED]


def test_closed_ticket_can_reopen() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.REOPENED in VALID_TRANSITIONS[TicketStatus.CLOSED]


def test_in_progress_can_escalate() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.ESCALATED in VALID_TRANSITIONS[TicketStatus.IN_PROGRESS]


def test_in_progress_can_go_on_hold() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.ON_HOLD in VALID_TRANSITIONS[TicketStatus.IN_PROGRESS]


def test_on_hold_cannot_go_to_new() -> None:
    from app.services.ticket_service import VALID_TRANSITIONS
    from app.models.ticket import TicketStatus

    assert TicketStatus.NEW not in VALID_TRANSITIONS[TicketStatus.ON_HOLD]


# ---------------------------------------------------------------------------
# Ticket number generation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ticket_number_format() -> None:
    from app.services.ticket_service import TicketService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 5
    db.execute = AsyncMock(return_value=mock_result)

    svc = TicketService(db)
    number = await svc.generate_ticket_number()

    assert number.startswith("TKT-")
    parts = number.split("-")
    assert len(parts) == 3
    assert len(parts[1]) == 8    # YYYYMMDD
    assert parts[2].isdigit()
    assert len(parts[2]) == 5   # zero-padded to 5 digits


@pytest.mark.asyncio
async def test_ticket_number_sequential() -> None:
    from app.services.ticket_service import TicketService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one.return_value = 99
    db.execute = AsyncMock(return_value=mock_result)

    svc = TicketService(db)
    number = await svc.generate_ticket_number()
    suffix = number.split("-")[2]
    assert suffix == "00100"  # 99 existing + 1 = 100


# ---------------------------------------------------------------------------
# FSM transition tests — db.get() pattern
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_status_transition_raises() -> None:
    """NEW → RESOLVED is not a valid FSM transition."""
    from app.core.exceptions import ValidationError
    from app.models.ticket import TicketStatus
    from app.services.ticket_service import TicketService

    db = _mock_db()
    ticket = _make_ticket(status=TicketStatus.NEW)
    db.get = AsyncMock(return_value=ticket)   # get_ticket uses db.get()

    svc = TicketService(db, actor_id=str(uuid.uuid4()))

    with pytest.raises(ValidationError, match="transition"):
        await svc.transition_status(ticket.id, TicketStatus.RESOLVED, uuid.uuid4())


@pytest.mark.asyncio
async def test_valid_status_transition_succeeds() -> None:
    from app.models.ticket import TicketStatus
    from app.services.ticket_service import TicketService

    db = _mock_db()
    ticket = _make_ticket(status=TicketStatus.NEW)
    db.get = AsyncMock(return_value=ticket)

    with patch("app.services.ticket_service.AuditService") as MockAudit:
        mock_audit_instance = MockAudit.return_value
        mock_audit_instance.log = AsyncMock()

        svc = TicketService(db, actor_id=str(uuid.uuid4()))
        updated = await svc.transition_status(ticket.id, TicketStatus.ACKNOWLEDGED, uuid.uuid4())

    assert updated.status == TicketStatus.ACKNOWLEDGED.value


@pytest.mark.asyncio
async def test_resolve_sets_resolved_at() -> None:
    from app.models.ticket import TicketStatus
    from app.services.ticket_service import TicketService

    db = _mock_db()
    ticket = _make_ticket(status=TicketStatus.IN_PROGRESS)
    ticket.resolved_at = None
    db.get = AsyncMock(return_value=ticket)

    with patch("app.services.ticket_service.AuditService") as MockAudit:
        mock_audit_instance = MockAudit.return_value
        mock_audit_instance.log = AsyncMock()

        svc = TicketService(db, actor_id=str(uuid.uuid4()))
        updated = await svc.transition_status(ticket.id, TicketStatus.RESOLVED, uuid.uuid4())

    assert updated.resolved_at is not None


@pytest.mark.asyncio
async def test_ticket_not_found_raises() -> None:
    from app.core.exceptions import NotFoundError
    from app.models.ticket import TicketStatus
    from app.services.ticket_service import TicketService

    db = _mock_db()
    db.get = AsyncMock(return_value=None)   # no ticket found

    svc = TicketService(db)
    with pytest.raises(NotFoundError):
        await svc.transition_status(uuid.uuid4(), TicketStatus.ACKNOWLEDGED, uuid.uuid4())


# ---------------------------------------------------------------------------
# Duplicate ticket logic
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_mark_duplicate_sets_flag() -> None:
    from app.models.ticket import TicketStatus
    from app.services.ticket_service import TicketService

    db = _mock_db()
    original = _make_ticket(status=TicketStatus.NEW)
    duplicate = _make_ticket(status=TicketStatus.NEW)
    duplicate.is_duplicate = False

    # mark_duplicate calls get_ticket twice via db.get
    db.get = AsyncMock(side_effect=[duplicate, original])

    with patch("app.services.ticket_service.AuditService") as MockAudit:
        mock_audit_instance = MockAudit.return_value
        mock_audit_instance.log = AsyncMock()

        svc = TicketService(db, actor_id=str(uuid.uuid4()))
        result = await svc.mark_duplicate(duplicate.id, original.id, uuid.uuid4())

    assert result.is_duplicate is True
    assert result.duplicate_of_id == original.id
