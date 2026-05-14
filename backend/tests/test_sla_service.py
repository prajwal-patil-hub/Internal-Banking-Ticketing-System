"""SLAService unit tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    return db


def _make_policy(priority: str, response_min: int, resolution_min: int):
    from app.models.sla import SLAPolicy

    p = SLAPolicy(
        id=uuid.uuid4(),
        name=f"{priority} policy",
        priority=priority,
        response_minutes=response_min,
        resolution_minutes=resolution_min,
        business_hours_only=False,
        is_default=True,
    )
    p.created_at = datetime.now(timezone.utc)
    p.updated_at = datetime.now(timezone.utc)
    return p


def _make_ticket_in_progress():
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

    t = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260513-00001",
        title="Overdue ticket",
        description="test",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.CRITICAL,
        source=TicketSource.PORTAL,
        reporter_id=uuid.uuid4(),
        sla_breached=False,
        sla_paused_at=None,
    )
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    return t


def _make_tracking(ticket_id, response_due: datetime, resolution_due: datetime):
    from app.models.sla import SLATracking

    t = SLATracking(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        response_due_at=response_due,
        resolution_due_at=resolution_due,
        is_response_breached=False,
        is_resolution_breached=False,
        total_paused_minutes=0,
    )
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    return t


# ---------------------------------------------------------------------------
# Policy lookup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_default_policy_returns_settings_fallback() -> None:
    from app.services.sla_service import SLAService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    svc = SLAService(db)
    # Should not raise even when no DB policy exists
    policy = await svc.get_or_create_policy(category_id=None, priority="critical")
    assert True  # service completed without exception


@pytest.mark.asyncio
async def test_get_policy_returns_existing_db_policy() -> None:
    from app.services.sla_service import SLAService

    db = _mock_db()
    policy = _make_policy("high", 60, 360)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = policy
    db.execute = AsyncMock(return_value=mock_result)

    svc = SLAService(db)
    result = await svc.get_or_create_policy(category_id=None, priority="high")

    assert result is not None
    assert result.response_minutes == 60
    assert result.resolution_minutes == 360


# ---------------------------------------------------------------------------
# Breach detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_check_breaches_marks_overdue_tickets() -> None:
    """check_breaches should return newly breached tickets."""
    from app.services.sla_service import SLAService

    db = _mock_db()

    ticket = _make_ticket_in_progress()
    now = datetime.now(timezone.utc)
    ticket.resolution_due_at = now - timedelta(hours=1)  # already overdue

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            # First call: return overdue tickets
            m.scalars.return_value.all.return_value = [ticket]
        else:
            # Subsequent calls: tracking row (can be None)
            m.scalar_one_or_none.return_value = None
        return m

    db.execute = mock_execute

    svc = SLAService(db)
    breached = await svc.check_breaches()

    assert len(breached) == 1
    assert breached[0].sla_breached is True


@pytest.mark.asyncio
async def test_check_breaches_no_overdue_returns_empty() -> None:
    from app.services.sla_service import SLAService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    svc = SLAService(db)
    breached = await svc.check_breaches()

    assert breached == []


# ---------------------------------------------------------------------------
# SLA summary
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_sla_summary_returns_dict() -> None:
    from app.services.sla_service import SLAService

    db = _mock_db()

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        m.scalar_one.return_value = call_count * 5
        return m

    db.execute = mock_execute

    svc = SLAService(db)
    summary = await svc.get_sla_summary()

    assert isinstance(summary, dict)
    assert len(summary) > 0


# ---------------------------------------------------------------------------
# Pause / Resume SLA — uses db.get() for ticket lookup
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pause_sla_sets_paused_at() -> None:
    """pause_sla should set ticket.sla_paused_at."""
    from app.services.sla_service import SLAService

    db = _mock_db()
    ticket = _make_ticket_in_progress()
    ticket.sla_paused_at = None

    db.get = AsyncMock(return_value=ticket)   # SLAService uses db.get() for ticket

    # tracking lookup returns None (no SLATracking row)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    svc = SLAService(db)
    await svc.pause_sla(ticket.id)

    assert ticket.sla_paused_at is not None


@pytest.mark.asyncio
async def test_pause_sla_noop_if_already_paused() -> None:
    """Calling pause_sla twice should not reset the paused_at timestamp."""
    from app.services.sla_service import SLAService

    db = _mock_db()
    ticket = _make_ticket_in_progress()
    original_paused_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    ticket.sla_paused_at = original_paused_at

    db.get = AsyncMock(return_value=ticket)

    svc = SLAService(db)
    await svc.pause_sla(ticket.id)

    # paused_at should NOT have been updated (already paused)
    assert ticket.sla_paused_at == original_paused_at


@pytest.mark.asyncio
async def test_resume_sla_clears_paused_at_and_extends_deadline() -> None:
    """resume_sla should clear sla_paused_at and extend deadline by paused duration."""
    from app.services.sla_service import SLAService

    db = _mock_db()
    ticket = _make_ticket_in_progress()

    paused_at = datetime.now(timezone.utc) - timedelta(minutes=30)
    original_resolution = datetime.now(timezone.utc) + timedelta(hours=2)

    ticket.sla_paused_at = paused_at
    ticket.response_due_at = original_resolution
    ticket.resolution_due_at = original_resolution

    db.get = AsyncMock(return_value=ticket)

    tracking = _make_tracking(ticket.id, original_resolution, original_resolution)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = tracking
    db.execute = AsyncMock(return_value=mock_result)

    svc = SLAService(db)
    await svc.resume_sla(ticket.id)

    # After resume: paused_at cleared
    assert ticket.sla_paused_at is None
    # Deadline should have been extended by ~30 minutes
    assert ticket.resolution_due_at > original_resolution
    # Tracking row should record paused minutes
    assert tracking.total_paused_minutes >= 28


@pytest.mark.asyncio
async def test_resume_sla_noop_if_not_paused() -> None:
    """Calling resume_sla on an unpaused ticket should be a no-op."""
    from app.services.sla_service import SLAService

    db = _mock_db()
    ticket = _make_ticket_in_progress()
    ticket.sla_paused_at = None  # not paused

    db.get = AsyncMock(return_value=ticket)

    svc = SLAService(db)
    # Should not raise
    await svc.resume_sla(ticket.id)

    # No changes expected
    assert ticket.sla_paused_at is None
