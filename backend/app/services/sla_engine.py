"""SLA engine — initial due-at, pause/resume, reset on reopen, breach scan.

Lifecycle hooks (call from TicketService / WorkflowService):
  - on_ticket_created  : insert sla_tracking with due_at = now + policy.minutes
  - on_status_changed  : pause when status -> on_hold, resume when leaving
  - on_reopened        : recompute due_at from the policy (fresh clock)

The breach detector is idempotent — re-running it within the same tick
won't double-flag a ticket because of the `breached.is_(False)` filter.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.enums import Priority
from app.models.sla import SLATracking
from app.models.ticket import Ticket
from app.repositories.sla_repo import SLAPolicyRepository, SLATrackingRepository

log = get_logger(__name__)


def _fallback_minutes(priority: str) -> int:
    return {
        Priority.CRITICAL.value: settings.SLA_CRITICAL_MINUTES,
        Priority.HIGH.value:     settings.SLA_HIGH_MINUTES,
        Priority.MEDIUM.value:   settings.SLA_MEDIUM_MINUTES,
        Priority.LOW.value:      settings.SLA_LOW_MINUTES,
    }.get(priority, settings.SLA_MEDIUM_MINUTES)


class SLAEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.policies = SLAPolicyRepository(db)
        self.tracking = SLATrackingRepository(db)

    async def _resolution_minutes_for(self, priority: str) -> int:
        policy = await self.policies.get(priority)
        if policy is not None:
            return policy.resolution_minutes
        return _fallback_minutes(priority)

    # ---- lifecycle hooks ------------------------------------------------

    async def on_ticket_created(self, ticket: Ticket) -> SLATracking:
        minutes = await self._resolution_minutes_for(ticket.priority)
        due_at = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        ticket.sla_due_at = due_at
        return await self.tracking.add(
            SLATracking(
                ticket_id=ticket.id,
                policy_priority=ticket.priority,
                due_at=due_at,
            )
        )

    async def on_paused(self, ticket: Ticket) -> None:
        row = await self.tracking.get_by_ticket(ticket.id)
        if row is None or row.paused_at is not None:
            return
        row.paused_at = datetime.now(timezone.utc)

    async def on_resumed(self, ticket: Ticket) -> None:
        row = await self.tracking.get_by_ticket(ticket.id)
        if row is None or row.paused_at is None:
            return
        now = datetime.now(timezone.utc)
        elapsed = int((now - row.paused_at).total_seconds())
        row.total_paused_seconds += max(elapsed, 0)
        row.due_at = row.due_at + timedelta(seconds=elapsed)
        row.paused_at = None
        ticket.sla_due_at = row.due_at

    async def on_reopened(self, ticket: Ticket) -> None:
        row = await self.tracking.get_by_ticket(ticket.id)
        minutes = await self._resolution_minutes_for(ticket.priority)
        new_due = datetime.now(timezone.utc) + timedelta(minutes=minutes)
        if row is None:
            row = await self.tracking.add(
                SLATracking(ticket_id=ticket.id, policy_priority=ticket.priority, due_at=new_due)
            )
        else:
            row.due_at = new_due
            row.breached = False
            row.breach_at = None
            row.paused_at = None
        ticket.sla_due_at = new_due

    # ---- breach detector -------------------------------------------------

    async def detect_breaches(self) -> list[uuid.UUID]:
        now = datetime.now(timezone.utc)
        rows = await self.tracking.find_due_unbreached(now=now)
        breached_ids: list[uuid.UUID] = []
        for r in rows:
            r.breached = True
            r.breach_at = now
            breached_ids.append(r.ticket_id)
        if breached_ids:
            log.info("sla_breach_detected", count=len(breached_ids))
        return breached_ids
