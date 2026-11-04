"""RoutingService unit tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.get = AsyncMock()
    return db


def _make_user(role_name: str = "agent"):
    from app.models.role import Role
    from app.models.user import User

    role = Role(id=uuid.uuid4(), name=role_name, description="")
    role.created_at = datetime.now(UTC)
    role.updated_at = datetime.now(UTC)

    user = User(
        id=uuid.uuid4(),
        email=f"agent-{uuid.uuid4().hex[:6]}@bank.com",
        full_name="Test Agent",
        password_hash="hashed",
        role_id=role.id,
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
    )
    user.role = role
    user.created_at = datetime.now(UTC)
    user.updated_at = datetime.now(UTC)
    return user


def _make_ticket(**kwargs):
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

    t = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260513-00001",
        title="Test",
        description="Test",
        status=TicketStatus.NEW,
        priority=TicketPriority.MEDIUM,
        source=TicketSource.PORTAL,
        reporter_id=uuid.uuid4(),
    )
    for k, v in kwargs.items():
        setattr(t, k, v)
    t.created_at = datetime.now(UTC)
    t.updated_at = datetime.now(UTC)
    return t


# ---------------------------------------------------------------------------
# Agent workload — returns list[dict]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_agent_workload_returns_list_of_dicts() -> None:
    """get_agent_workload returns list of dicts with user_id, email, etc."""
    from app.services.routing_service import RoutingService

    db = _mock_db()

    from datetime import date, timedelta

    today = date.today()

    def _row(email, name, open_count, leave_from=None, leave_to=None):
        r = MagicMock()
        r.id = uuid.uuid4()
        r.email = email
        r.full_name = name
        r.role = "agent"
        r.open_count = open_count
        # Real values, not MagicMocks: the service compares these to today's
        # date to decide whether someone is on leave, and a MagicMock compares
        # as anything.
        r.leave_from = leave_from
        r.leave_to = leave_to
        r.leave_note = None
        return r

    # The service executes a JOIN query and calls .all() on the result
    row1 = _row("agent1@bank.com", "Agent One", 5)
    row2 = _row("agent2@bank.com", "Agent Two", 2)
    row3 = _row("agent3@bank.com", "Agent Three", 0,
                today - timedelta(days=1), today + timedelta(days=3))

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2, row3]
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    workload = await svc.get_agent_workload()

    assert isinstance(workload, list)
    assert len(workload) == 3
    assert workload[0]["email"] == "agent1@bank.com"
    assert workload[1]["open_count"] == 2

    # Someone on leave is still listed — a supervisor may knowingly assign to
    # them — but is marked so the UI can say so and auto-routing can skip them.
    assert workload[0]["on_leave"] is False
    assert workload[2]["on_leave"] is True
    assert workload[2]["leave_to"] == (today + timedelta(days=3)).isoformat()


@pytest.mark.asyncio
async def test_get_agent_workload_empty() -> None:
    from app.services.routing_service import RoutingService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.all.return_value = []
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    workload = await svc.get_agent_workload()

    assert workload == []


# ---------------------------------------------------------------------------
# Best assignee — uses scalar_one_or_none()
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_best_assignee_returns_agent() -> None:
    """find_best_assignee uses execute().scalar_one_or_none() to get a User."""
    from app.services.routing_service import RoutingService

    db = _mock_db()
    agent = _make_user()
    ticket = _make_ticket(branch_id=None)  # no branch → global fallback

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = agent
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    best = await svc.find_best_assignee(ticket)

    assert best is not None
    assert best.id == agent.id


@pytest.mark.asyncio
async def test_find_best_assignee_returns_none_when_no_agents() -> None:
    from app.services.routing_service import RoutingService

    db = _mock_db()
    ticket = _make_ticket(branch_id=None)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    best = await svc.find_best_assignee(ticket)

    assert best is None


@pytest.mark.asyncio
async def test_find_best_assignee_branch_match_preferred() -> None:
    """When ticket has branch_id, branch-matched agent is preferred."""
    from app.services.routing_service import RoutingService

    db = _mock_db()
    branch_id = uuid.uuid4()
    branch_agent = _make_user()
    global_agent = _make_user()
    ticket = _make_ticket(branch_id=branch_id)

    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            # Branch-scoped query returns branch_agent
            m.scalar_one_or_none.return_value = branch_agent
        else:
            m.scalar_one_or_none.return_value = global_agent
        return m

    db.execute = mock_execute

    svc = RoutingService(db)
    best = await svc.find_best_assignee(ticket)

    # Should have used the branch-matched agent (first query result)
    assert best is not None
    assert best.id == branch_agent.id


# ---------------------------------------------------------------------------
# Auto-route
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_auto_route_assigns_ticket() -> None:
    from app.models.ticket import TicketStatus
    from app.services.routing_service import RoutingService

    db = _mock_db()
    agent = _make_user()
    ticket = _make_ticket(status=TicketStatus.NEW, branch_id=None)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = agent
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    assignee, reason = await svc.auto_route_ticket(ticket)

    assert assignee is not None
    assert assignee.id == agent.id
    assert ticket.assignee_id == agent.id
    assert ticket.status == TicketStatus.ASSIGNED.value
    assert isinstance(reason, str)
    assert len(reason) > 0


@pytest.mark.asyncio
async def test_auto_route_returns_no_agent_reason_when_empty() -> None:
    from app.services.routing_service import RoutingService

    db = _mock_db()
    ticket = _make_ticket(branch_id=None)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    assignee, reason = await svc.auto_route_ticket(ticket)

    assert assignee is None
    assert "No available agent" in reason or len(reason) > 0


@pytest.mark.asyncio
async def test_auto_route_does_not_regress_resolved_ticket() -> None:
    """A resolved ticket should stay RESOLVED after routing attempt."""
    from app.models.ticket import TicketStatus
    from app.services.routing_service import RoutingService

    db = _mock_db()
    agent = _make_user()
    ticket = _make_ticket(status=TicketStatus.RESOLVED, branch_id=None)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = agent
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    _assignee, _reason = await svc.auto_route_ticket(ticket)

    # Resolved is not in (NEW, ACKNOWLEDGED) so status should not change
    assert ticket.status == TicketStatus.RESOLVED.value
