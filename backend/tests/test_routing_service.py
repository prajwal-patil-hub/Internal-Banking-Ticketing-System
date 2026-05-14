"""RoutingService unit tests."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
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
    from app.models.user import User
    from app.models.role import Role

    role = Role(id=uuid.uuid4(), name=role_name, description="")
    role.created_at = datetime.now(timezone.utc)
    role.updated_at = datetime.now(timezone.utc)

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
    user.created_at = datetime.now(timezone.utc)
    user.updated_at = datetime.now(timezone.utc)
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
    t.created_at = datetime.now(timezone.utc)
    t.updated_at = datetime.now(timezone.utc)
    return t


# ---------------------------------------------------------------------------
# Agent workload — returns list[dict]
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_agent_workload_returns_list_of_dicts() -> None:
    """get_agent_workload returns list of dicts with user_id, email, etc."""
    from app.services.routing_service import RoutingService

    db = _mock_db()

    # The service executes a JOIN query and calls .all() on the result
    row1 = MagicMock()
    row1.id = uuid.uuid4()
    row1.email = "agent1@bank.com"
    row1.full_name = "Agent One"
    row1.open_count = 5

    row2 = MagicMock()
    row2.id = uuid.uuid4()
    row2.email = "agent2@bank.com"
    row2.full_name = "Agent Two"
    row2.open_count = 2

    mock_result = MagicMock()
    mock_result.all.return_value = [row1, row2]
    db.execute = AsyncMock(return_value=mock_result)

    svc = RoutingService(db)
    workload = await svc.get_agent_workload()

    assert isinstance(workload, list)
    assert len(workload) == 2
    assert workload[0]["email"] == "agent1@bank.com"
    assert workload[1]["open_count"] == 2


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
    assignee, reason = await svc.auto_route_ticket(ticket)

    # Resolved is not in (NEW, ACKNOWLEDGED) so status should not change
    assert ticket.status == TicketStatus.RESOLVED.value
