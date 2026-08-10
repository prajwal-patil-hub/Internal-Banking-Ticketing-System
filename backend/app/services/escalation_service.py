"""Escalation engine.

The pieces of escalation all existed and none of them were connected. Rules sat
in `escalation_rules` and were rendered by the Escalations page, but no code
ever evaluated one. `escalation_events` had a model, an endpoint and a table —
and the only writer was the development seed, so the event log would show its
three seeded rows forever no matter how many tickets escalated. The SLA worker
marked breaches and logged a line. Everything past "the ticket turns red" was a
human noticing.

This module joins them: on breach it finds the applicable rule, moves the
ticket, records the event, and notifies the target.

Two properties matter more than the routing itself:

- **Escalating twice is worse than not escalating.** A worker that runs every
  five minutes will revisit the same breached ticket forever, so an open event
  for the same ticket and trigger suppresses another.
- **A failed notification must not lose the escalation.** The email is sent
  after the state change is durable, and a send failure is logged rather than
  raised — an unsent email is recoverable, a silently dropped escalation is not.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.escalation import EscalationEvent, EscalationRule, EscalationTrigger
from app.models.role import Role
from app.models.ticket import OPEN_STATUS_VALUES, Ticket, TicketStatus
from app.models.user import User

log = get_logger(__name__)

#: Priority ordering. A rule's `priority_threshold` is a *minimum*: a rule set
#: to "high" also covers critical, which is why this needs an ordering rather
#: than an equality check.
_PRIORITY_RANK = {"low": 0, "medium": 1, "high": 2, "critical": 3}


@dataclass
class EscalationOutcome:
    """What happened, for the caller to log or surface."""

    escalated: bool
    reason: str
    event: EscalationEvent | None = None
    assignee: User | None = None
    rule: EscalationRule | None = None


def _priority_value(ticket: Ticket) -> str:
    return ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value


def _status_value(ticket: Ticket) -> str:
    return ticket.status if isinstance(ticket.status, str) else ticket.status.value


class EscalationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Rule matching
    # ------------------------------------------------------------------

    async def find_rule(
        self, ticket: Ticket, trigger: EscalationTrigger
    ) -> EscalationRule | None:
        """The most specific active rule that covers this ticket.

        Specificity beats declaration order: a rule naming this ticket's
        category is preferred over a catch-all, and among equals the one with
        the highest priority threshold wins. Otherwise "any regulatory matter"
        would shadow "critical payment breaches" purely by being created first.
        """
        rules = (await self.db.execute(
            select(EscalationRule).where(
                EscalationRule.trigger == trigger,
                EscalationRule.is_active.is_(True),
            )
        )).scalars().all()

        ticket_rank = _PRIORITY_RANK.get(_priority_value(ticket), 0)
        candidates: list[tuple[int, int, EscalationRule]] = []

        for rule in rules:
            if rule.category_id is not None and rule.category_id != ticket.category_id:
                continue
            threshold = rule.priority_threshold
            if threshold:
                if ticket_rank < _PRIORITY_RANK.get(threshold, 0):
                    continue
            # (category-specific, threshold strictness) — higher sorts first.
            candidates.append((
                1 if rule.category_id is not None else 0,
                _PRIORITY_RANK.get(threshold or "low", 0),
                rule,
            ))

        if not candidates:
            return None
        candidates.sort(key=lambda c: (c[0], c[1]), reverse=True)
        return candidates[0][2]

    # ------------------------------------------------------------------
    # Duplicate suppression
    # ------------------------------------------------------------------

    async def has_open_escalation(
        self, ticket_id: uuid.UUID, trigger: EscalationTrigger
    ) -> bool:
        """True when this ticket already has an unresolved event of this kind.

        The breach worker re-runs every five minutes over the same set of
        overdue tickets, so without this the event log would gain a row per
        ticket per run and the escalation target would be emailed forever.
        """
        existing = (await self.db.execute(
            select(EscalationEvent.id).where(
                EscalationEvent.ticket_id == ticket_id,
                EscalationEvent.trigger == trigger,
                EscalationEvent.resolved_at.is_(None),
            ).limit(1)
        )).first()
        return existing is not None

    # ------------------------------------------------------------------
    # Target selection
    # ------------------------------------------------------------------

    async def find_target(self, rule: EscalationRule | None) -> User | None:
        """Who the ticket goes to: the named user, or the least-loaded holder
        of the rule's role."""
        if rule is not None and rule.escalate_to_user_id:
            named = await self.db.get(User, rule.escalate_to_user_id)
            if named is not None and named.is_active:
                return named

        role_name = rule.escalate_to_role if rule is not None else "supervisor"

        open_counts = (
            select(
                Ticket.assignee_id.label("user_id"),
                func.count(Ticket.id).label("open_count"),
            )
            .where(Ticket.status.in_(OPEN_STATUS_VALUES))
            .where(Ticket.assignee_id.isnot(None))
            .group_by(Ticket.assignee_id)
            .subquery()
        )

        return (await self.db.execute(
            select(User)
            .join(Role, Role.id == User.role_id)
            .outerjoin(open_counts, User.id == open_counts.c.user_id)
            .where(User.is_active.is_(True), Role.name == role_name)
            .order_by(func.coalesce(open_counts.c.open_count, 0).asc())
            .limit(1)
        )).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Escalate
    # ------------------------------------------------------------------

    async def escalate(
        self,
        ticket: Ticket,
        *,
        trigger: EscalationTrigger,
        reason: str,
        actor_id: uuid.UUID | None = None,
        rule: EscalationRule | None = None,
        reassign: bool = True,
    ) -> EscalationOutcome:
        """Move the ticket to escalated, record it, and pick a new owner.

        The caller commits. Nothing here sends email — notification happens
        after the transaction is durable, so a mail failure cannot roll back
        the escalation.
        """
        if await self.has_open_escalation(ticket.id, trigger):
            return EscalationOutcome(False, "Already escalated for this trigger.")

        if _status_value(ticket) not in OPEN_STATUS_VALUES:
            return EscalationOutcome(False, "Ticket is already resolved or closed.")

        if rule is None:
            rule = await self.find_rule(ticket, trigger)

        target = await self.find_target(rule) if reassign else None
        now = datetime.now(UTC)

        previous_assignee = ticket.assignee_id
        if target is not None:
            ticket.assignee_id = target.id
        ticket.status = TicketStatus.ESCALATED

        event = EscalationEvent(
            id=uuid.uuid4(),
            ticket_id=ticket.id,
            rule_id=rule.id if rule is not None else None,
            trigger=trigger,
            triggered_at=now,
            escalated_to_id=target.id if target is not None else None,
            escalated_by_id=actor_id,
            reason=reason[:500],
        )
        self.db.add(event)
        await self.db.flush()

        log.info(
            "escalation.raised",
            ticket_id=str(ticket.id),
            ticket_number=ticket.ticket_number,
            trigger=trigger.value,
            rule=rule.name if rule is not None else None,
            from_assignee=str(previous_assignee) if previous_assignee else None,
            to_assignee=str(target.id) if target is not None else None,
        )
        return EscalationOutcome(True, reason, event=event, assignee=target, rule=rule)

    # ------------------------------------------------------------------
    # Breach handling — the path the SLA worker takes
    # ------------------------------------------------------------------

    async def escalate_breached(self, ticket: Ticket) -> EscalationOutcome:
        """Apply the SLA-breach rules to a ticket that has just gone overdue."""
        rule = await self.find_rule(ticket, EscalationTrigger.SLA_BREACH)

        if rule is None:
            return EscalationOutcome(False, "No escalation rule matches this ticket.")

        # `trigger_after_minutes` is a grace period past the deadline, so a
        # ticket a minute late is not escalated the instant the worker sees it.
        if rule.trigger_after_minutes and ticket.resolution_due_at:
            due = ticket.resolution_due_at
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)
            overdue_by = datetime.now(UTC) - due
            if overdue_by < timedelta(minutes=rule.trigger_after_minutes):
                return EscalationOutcome(
                    False,
                    f"Overdue by {overdue_by} — inside the "
                    f"{rule.trigger_after_minutes} minute grace period.",
                )

        overdue_desc = "past its resolution deadline"
        if ticket.resolution_due_at:
            due = ticket.resolution_due_at
            if due.tzinfo is None:
                due = due.replace(tzinfo=UTC)
            hours = (datetime.now(UTC) - due).total_seconds() / 3600
            overdue_desc = f"{hours:.1f}h past its resolution deadline"

        return await self.escalate(
            ticket,
            trigger=EscalationTrigger.SLA_BREACH,
            reason=f"SLA breached — {overdue_desc}. Rule: {rule.name}.",
            rule=rule,
        )


async def notify_escalation_outcome(
    db: AsyncSession, ticket: Ticket, outcome: EscalationOutcome
) -> None:
    """Send the emails for a committed escalation.

    Deliberately separate from `escalate` and called after the commit: a
    delivery failure should cost an email, not the escalation record. Any
    exception is swallowed for the same reason.
    """
    if not outcome.escalated:
        return

    try:
        from app.services.notification_service import NotificationService

        notifier = NotificationService(db)

        if outcome.assignee is not None:
            await notifier.notify_escalation(
                ticket=ticket,
                escalatee_email=outcome.assignee.email,
                reason=outcome.reason,
            )

        if managers := settings.manager_email_list:
            await notifier.notify_sla_breach(ticket=ticket, manager_emails=managers)
    except Exception as exc:  # noqa: BLE001 - see docstring
        log.warning(
            "escalation.notify_failed",
            ticket_id=str(ticket.id),
            error=str(exc),
        )
