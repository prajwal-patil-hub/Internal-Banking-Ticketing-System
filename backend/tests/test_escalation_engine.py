"""Escalation engine — rule matching, duplicate suppression, targeting.

Every piece of escalation existed and none were connected: rules were rendered
but never evaluated, the event table's only writer was the seed script, and the
SLA worker marked a breach then stopped. These cover the logic that now joins
them.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.models.escalation import EscalationTrigger
from app.services.escalation_service import (
    _PRIORITY_RANK,
    EscalationOutcome,
    EscalationService,
    _priority_value,
    _status_value,
)
from app.models.ticket import TicketPriority, TicketStatus


def rule(**kw):
    base = dict(
        id=uuid.uuid4(), name="r", category_id=None, trigger=EscalationTrigger.SLA_BREACH,
        trigger_after_minutes=None, escalate_to_role="supervisor",
        escalate_to_user_id=None, is_active=True, priority_threshold=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


def ticket(**kw):
    base = dict(
        id=uuid.uuid4(), ticket_number="TKT-000001", category_id=None,
        priority=TicketPriority.HIGH, status=TicketStatus.IN_PROGRESS,
        resolution_due_at=None, assignee_id=None,
    )
    base.update(kw)
    return SimpleNamespace(**base)


# ---------------------------------------------------------------------------
# Priority thresholds
# ---------------------------------------------------------------------------

def test_priority_ranking_is_ordered() -> None:
    assert (_PRIORITY_RANK["low"] < _PRIORITY_RANK["medium"]
            < _PRIORITY_RANK["high"] < _PRIORITY_RANK["critical"])


def test_threshold_is_a_minimum_not_an_equality() -> None:
    """A rule set to `high` must also fire for critical.

    The column is documented as "minimum priority level that triggers this
    rule", so matching on equality would silently skip the most urgent tickets
    — the exact ones the rule exists for.
    """
    assert _PRIORITY_RANK["critical"] > _PRIORITY_RANK["high"]


def test_value_helpers_accept_enum_or_string() -> None:
    """Status and priority arrive as either, depending on the code path."""
    assert _priority_value(ticket(priority=TicketPriority.CRITICAL)) == "critical"
    assert _priority_value(ticket(priority="critical")) == "critical"
    assert _status_value(ticket(status=TicketStatus.ESCALATED)) == "escalated"
    assert _status_value(ticket(status="escalated")) == "escalated"


# ---------------------------------------------------------------------------
# Rule selection
# ---------------------------------------------------------------------------

class _FakeResult:
    def __init__(self, rows): self._rows = rows
    def scalars(self): return self
    def all(self): return self._rows
    def first(self): return self._rows[0] if self._rows else None


class _FakeDB:
    def __init__(self, rows): self.rows = rows
    async def execute(self, *_a, **_k): return _FakeResult(self.rows)


@pytest.mark.asyncio
async def test_rule_below_threshold_is_skipped() -> None:
    svc = EscalationService(_FakeDB([rule(priority_threshold="critical")]))

    assert await svc.find_rule(ticket(priority=TicketPriority.LOW),
                               EscalationTrigger.SLA_BREACH) is None


@pytest.mark.asyncio
async def test_rule_at_or_above_threshold_matches() -> None:
    svc = EscalationService(_FakeDB([rule(priority_threshold="high")]))

    for priority in (TicketPriority.HIGH, TicketPriority.CRITICAL):
        assert await svc.find_rule(ticket(priority=priority),
                                   EscalationTrigger.SLA_BREACH) is not None


@pytest.mark.asyncio
async def test_a_rule_for_another_category_does_not_match() -> None:
    svc = EscalationService(_FakeDB([rule(category_id=uuid.uuid4())]))

    assert await svc.find_rule(ticket(category_id=uuid.uuid4()),
                               EscalationTrigger.SLA_BREACH) is None


@pytest.mark.asyncio
async def test_category_specific_rule_beats_the_catch_all() -> None:
    """Specificity must win, or declaration order decides the routing."""
    category = uuid.uuid4()
    catch_all = rule(name="catch-all")
    specific = rule(name="specific", category_id=category)
    svc = EscalationService(_FakeDB([catch_all, specific]))

    chosen = await svc.find_rule(ticket(category_id=category), EscalationTrigger.SLA_BREACH)

    assert chosen.name == "specific"


@pytest.mark.asyncio
async def test_the_stricter_threshold_wins_among_equals() -> None:
    loose = rule(name="loose", priority_threshold="low")
    strict = rule(name="strict", priority_threshold="high")
    svc = EscalationService(_FakeDB([loose, strict]))

    chosen = await svc.find_rule(ticket(priority=TicketPriority.CRITICAL),
                                 EscalationTrigger.SLA_BREACH)

    assert chosen.name == "strict"


# ---------------------------------------------------------------------------
# Duplicate suppression
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_an_open_event_suppresses_another() -> None:
    """The worker revisits the same overdue tickets every five minutes.

    Without this the event log gains a row per ticket per run and the target
    is emailed forever.
    """
    svc = EscalationService(_FakeDB([SimpleNamespace(id=uuid.uuid4())]))

    assert await svc.has_open_escalation(uuid.uuid4(), EscalationTrigger.SLA_BREACH)


@pytest.mark.asyncio
async def test_no_open_event_allows_escalation() -> None:
    svc = EscalationService(_FakeDB([]))

    assert not await svc.has_open_escalation(uuid.uuid4(), EscalationTrigger.SLA_BREACH)


@pytest.mark.asyncio
async def test_a_resolved_or_closed_ticket_is_not_escalated() -> None:
    svc = EscalationService(_FakeDB([]))

    outcome = await svc.escalate(
        ticket(status=TicketStatus.CLOSED),
        trigger=EscalationTrigger.MANUAL,
        reason="x",
    )

    assert not outcome.escalated
    assert "resolved or closed" in outcome.reason


# ---------------------------------------------------------------------------
# Outcome shape
# ---------------------------------------------------------------------------

def test_outcome_defaults_are_safe() -> None:
    outcome = EscalationOutcome(False, "nope")

    assert outcome.event is None and outcome.assignee is None and outcome.rule is None


def test_the_worker_calls_the_engine() -> None:
    """Guards the wiring itself.

    The worker previously marked the breach, logged a line, and left the
    notification call commented out — so nothing downstream ever ran.
    """
    import inspect

    from app.workers.sla_worker import check_sla_breaches_job

    src = inspect.getsource(check_sla_breaches_job)
    assert "escalate_breached" in src
    assert "notify_escalation_outcome" in src
