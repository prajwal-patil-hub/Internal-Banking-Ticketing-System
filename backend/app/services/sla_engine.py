"""SLA engine — response + resolution clocks, pause/resume, breach scan.

Two clocks per ticket (banking-standard):
  - response_due_at   = now + policy.response_minutes  (cleared on first agent reply)
  - due_at            = now + policy.resolution_minutes (paused on On Hold)

Lifecycle hooks (call from TicketService / WorkflowService):
  - on_ticket_created  : insert sla_tracking, set both clocks
  - on_first_response  : clear response_due_at (and the breached flag stays as-is)
  - on_paused / resumed: pause/resume the resolution clock
  - on_reopened        : reset both clocks fresh from the policy

The breach detector is idempotent — re-running it within the same tick
won't double-flag a ticket because of the `*breached.is_(False)` filter.
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

# Sensible response defaults (in minutes). Banks usually want a much
# shorter response than resolution clock; if no policy row is found we
# fall back to one quarter of the resolution minutes.
_RESPONSE_FALLBACK_RATIO = 0.25


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

    async def _minutes_for(self, priority: str) -> tuple[int, int]:
        """Return (response_minutes, resolution_minutes)."""
        policy = await self.policies.get(priority)
        if policy is not None:
            return policy.response_minutes, policy.resolution_minutes
        resolution = _fallback_minutes(priority)
        response = max(1, int(resolution * _RESPONSE_FALLBACK_RATIO))
        return response, resolution

    # ---- lifecycle hooks ------------------------------------------------

    async def on_ticket_created(self, ticket: Ticket) -> SLATracking:
        response_min, resolution_min = await self._minutes_for(ticket.priority)
        now = datetime.now(timezone.utc)
        due_at = now + timedelta(minutes=resolution_min)
        response_due_at = now + timedelta(minutes=response_min)
        ticket.sla_due_at = due_at
        return await self.tracking.add(
            SLATracking(
                ticket_id=ticket.id,
                policy_priority=ticket.priority,
                due_at=due_at,
                response_due_at=response_due_at,
            )
        )

    async def on_first_response(self, ticket: Ticket) -> None:
        """Called when the first non-internal agent comment lands."""
        row = await self.tracking.get_by_ticket(ticket.id)
        if row is None:
            return
        row.response_due_at = None
        # response_breached intentionally stays — it records that the SLA
        # was missed even after the response eventually arrived.

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
        response_min, resolution_min = await self._minutes_for(ticket.priority)
        now = datetime.now(timezone.utc)
        new_due = now + timedelta(minutes=resolution_min)
        new_response_due = now + timedelta(minutes=response_min)
        if row is None:
            row = await self.tracking.add(
                SLATracking(
                    ticket_id=ticket.id,
                    policy_priority=ticket.priority,
                    due_at=new_due,
                    response_due_at=new_response_due,
                )
            )
        else:
            row.due_at = new_due
            row.breached = False
            row.breach_at = None
            row.paused_at = None
            row.response_due_at = new_response_due
            row.response_breached = False
            row.response_breach_at = None
        ticket.sla_due_at = new_due

    # ---- breach detector -------------------------------------------------

    async def detect_breaches(self) -> list[uuid.UUID]:
        """Detect resolution + response breaches in one pass.

        Returns the ticket ids that *newly* breached resolution SLA so
        the caller can raise an Escalation row per ticket. Response
        breaches are recorded but don't auto-escalate (banks usually
        prefer a softer signal there — supervisor pings only).
        """
        now = datetime.now(timezone.utc)

        # Resolution breaches
        resolution = await self.tracking.find_due_unbreached(now=now)
        breached_ids: list[uuid.UUID] = []
        for r in resolution:
            r.breached = True
            r.breach_at = now
            breached_ids.append(r.ticket_id)
        if breached_ids:
            log.info("sla_resolution_breach", count=len(breached_ids))

        # Response breaches — separate query, separate flag.
        response = await self.tracking.find_response_due_unbreached(now=now)
        response_breached_ids: list[uuid.UUID] = []
        for r in response:
            r.response_breached = True
            r.response_breach_at = now
            response_breached_ids.append(r.ticket_id)
        if response_breached_ids:
            log.info("sla_response_breach", count=len(response_breached_ids))

        return breached_ids
