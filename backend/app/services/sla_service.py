"""SLA service — applies, monitors, and pauses SLA deadlines on tickets.

Business rules:
- Policy lookup: category+priority → category-only → priority-only → default.
- Deadlines are computed from ticket.created_at (or now if already created).
- Pause/resume adjusts resolution_due_at by the elapsed pause duration.
- check_breaches() is intended to run on a periodic scheduler (e.g. every minute).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.logging import get_logger
from app.models.sla import SLAPolicy, SLATracking
from app.models.ticket import Ticket, TicketPriority, TicketStatus

log = get_logger(__name__)

# Open statuses where SLA is still running
_OPEN_STATUSES = {
    TicketStatus.NEW.value,
    TicketStatus.ACKNOWLEDGED.value,
    TicketStatus.ASSIGNED.value,
    TicketStatus.IN_PROGRESS.value,
    TicketStatus.ESCALATED.value,
    TicketStatus.REOPENED.value,
}

# Default response/resolution minutes when no DB policy exists
_DEFAULTS: dict[str, tuple[int, int]] = {
    TicketPriority.CRITICAL.value: (
        settings.SLA_CRITICAL_MINUTES // 4,
        settings.SLA_CRITICAL_MINUTES,
    ),
    TicketPriority.HIGH.value: (
        settings.SLA_HIGH_MINUTES // 4,
        settings.SLA_HIGH_MINUTES,
    ),
    TicketPriority.MEDIUM.value: (
        settings.SLA_MEDIUM_MINUTES // 4,
        settings.SLA_MEDIUM_MINUTES,
    ),
    TicketPriority.LOW.value: (
        settings.SLA_LOW_MINUTES // 4,
        settings.SLA_LOW_MINUTES,
    ),
}


class SLAService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Policy lookup
    # ------------------------------------------------------------------

    async def get_or_create_policy(
        self,
        category_id: uuid.UUID | None,
        priority: str,
    ) -> SLAPolicy | None:
        """Return the best matching SLA policy for the given category+priority."""
        # 1. Exact category + priority match
        if category_id is not None:
            stmt = select(SLAPolicy).where(
                SLAPolicy.category_id == category_id,
                SLAPolicy.priority == priority,
                SLAPolicy.is_default.is_(False),
            )
            policy = (await self.db.execute(stmt)).scalar_one_or_none()
            if policy:
                return policy

        # 2. Priority match on default policy
        stmt = select(SLAPolicy).where(
            SLAPolicy.priority == priority,
            SLAPolicy.is_default.is_(True),
        )
        policy = (await self.db.execute(stmt)).scalar_one_or_none()
        if policy:
            return policy

        # 3. Any default policy
        stmt = select(SLAPolicy).where(SLAPolicy.is_default.is_(True)).limit(1)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    # ------------------------------------------------------------------
    # Apply SLA to a ticket
    # ------------------------------------------------------------------

    async def apply_to_ticket(self, ticket: Ticket) -> None:
        """Calculate and stamp SLA deadlines on *ticket*, then upsert SLATracking."""
        policy = await self.get_or_create_policy(
            category_id=ticket.category_id,
            priority=ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value,
        )

        now = datetime.now(timezone.utc)
        base_time: datetime = ticket.created_at if ticket.created_at.tzinfo else now

        if policy:
            resp_minutes = policy.response_minutes
            res_minutes = policy.resolution_minutes
            policy_id: uuid.UUID | None = policy.id
        else:
            prio_key = (
                ticket.priority if isinstance(ticket.priority, str) else ticket.priority.value
            )
            resp_minutes, res_minutes = _DEFAULTS.get(prio_key, (240, 1440))
            policy_id = None

        response_due = base_time + timedelta(minutes=resp_minutes)
        resolution_due = base_time + timedelta(minutes=res_minutes)

        ticket.sla_policy_id = policy_id
        ticket.response_due_at = response_due
        ticket.resolution_due_at = resolution_due

        # Upsert SLATracking
        stmt = select(SLATracking).where(SLATracking.ticket_id == ticket.id)
        tracking = (await self.db.execute(stmt)).scalar_one_or_none()

        if tracking is None:
            tracking = SLATracking(
                ticket_id=ticket.id,
                policy_id=policy_id,
                response_due_at=response_due,
                resolution_due_at=resolution_due,
            )
            self.db.add(tracking)
        else:
            tracking.policy_id = policy_id
            tracking.response_due_at = response_due
            tracking.resolution_due_at = resolution_due

        await self.db.flush()
        log.info(
            "sla.applied",
            ticket_id=str(ticket.id),
            policy_id=str(policy_id),
            response_due=response_due.isoformat(),
            resolution_due=resolution_due.isoformat(),
        )

    # ------------------------------------------------------------------
    # Breach detection
    # ------------------------------------------------------------------

    async def check_breaches(self) -> list[Ticket]:
        """
        Check all open tickets for SLA breaches.

        Marks ticket.sla_breached = True and SLATracking breach flags for any
        newly breached tickets. Returns the list of newly breached Ticket objects.
        """
        now = datetime.now(timezone.utc)
        stmt = (
            select(Ticket)
            .where(
                Ticket.status.in_(_OPEN_STATUSES),
                Ticket.sla_breached.is_(False),
                Ticket.resolution_due_at.isnot(None),
                Ticket.resolution_due_at < now,
                Ticket.sla_paused_at.is_(None),
            )
        )
        tickets = list((await self.db.execute(stmt)).scalars().all())
        newly_breached: list[Ticket] = []

        for ticket in tickets:
            ticket.sla_breached = True
            newly_breached.append(ticket)

            # Update SLATracking
            track_stmt = select(SLATracking).where(SLATracking.ticket_id == ticket.id)
            tracking = (await self.db.execute(track_stmt)).scalar_one_or_none()
            if tracking:
                tracking.is_resolution_breached = True

            log.warning(
                "sla.breached",
                ticket_id=str(ticket.id),
                ticket_number=ticket.ticket_number,
                resolution_due=str(ticket.resolution_due_at),
            )

        if newly_breached:
            await self.db.flush()

        return newly_breached

    # ------------------------------------------------------------------
    # Pause / Resume
    # ------------------------------------------------------------------

    async def pause_sla(self, ticket_id: uuid.UUID) -> None:
        """Pause the SLA clock for a ticket (e.g. awaiting customer info)."""
        ticket = await self.db.get(Ticket, ticket_id)
        if ticket is None:
            log.warning("sla.pause.ticket_not_found", ticket_id=str(ticket_id))
            return

        if ticket.sla_paused_at is not None:
            log.debug("sla.already_paused", ticket_id=str(ticket_id))
            return

        now = datetime.now(timezone.utc)
        ticket.sla_paused_at = now

        # Also record in tracking row
        stmt = select(SLATracking).where(SLATracking.ticket_id == ticket_id)
        tracking = (await self.db.execute(stmt)).scalar_one_or_none()
        if tracking:
            tracking.paused_at = now

        await self.db.flush()
        log.info("sla.paused", ticket_id=str(ticket_id))

    async def resume_sla(self, ticket_id: uuid.UUID) -> None:
        """Resume the SLA clock and extend deadlines by the paused duration."""
        ticket = await self.db.get(Ticket, ticket_id)
        if ticket is None:
            log.warning("sla.resume.ticket_not_found", ticket_id=str(ticket_id))
            return

        if ticket.sla_paused_at is None:
            log.debug("sla.not_paused", ticket_id=str(ticket_id))
            return

        now = datetime.now(timezone.utc)
        paused_duration = now - ticket.sla_paused_at

        # Extend deadlines by paused duration
        if ticket.response_due_at is not None:
            ticket.response_due_at = ticket.response_due_at + paused_duration
        if ticket.resolution_due_at is not None:
            ticket.resolution_due_at = ticket.resolution_due_at + paused_duration

        ticket.sla_paused_at = None

        # Update tracking row
        stmt = select(SLATracking).where(SLATracking.ticket_id == ticket_id)
        tracking = (await self.db.execute(stmt)).scalar_one_or_none()
        if tracking:
            paused_minutes = int(paused_duration.total_seconds() / 60)
            tracking.total_paused_minutes += paused_minutes
            tracking.paused_at = None
            if ticket.response_due_at:
                tracking.response_due_at = ticket.response_due_at
            if ticket.resolution_due_at:
                tracking.resolution_due_at = ticket.resolution_due_at

        await self.db.flush()
        log.info(
            "sla.resumed",
            ticket_id=str(ticket_id),
            paused_minutes=int(paused_duration.total_seconds() / 60),
        )

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    async def get_sla_summary(self) -> dict:
        """Return aggregated SLA compliance statistics across all open tickets."""
        now = datetime.now(timezone.utc)

        open_stmt = select(Ticket).where(Ticket.status.in_(_OPEN_STATUSES))
        open_tickets = list((await self.db.execute(open_stmt)).scalars().all())

        total = len(open_tickets)
        breached = sum(1 for t in open_tickets if t.sla_breached)
        at_risk = sum(
            1
            for t in open_tickets
            if not t.sla_breached
            and t.resolution_due_at is not None
            and (t.resolution_due_at - now).total_seconds() < 3600  # within 1 hour
        )
        on_time = total - breached - at_risk
        compliance_rate = (on_time / total * 100.0) if total > 0 else 100.0

        return {
            "total_open": total,
            "on_time": max(on_time, 0),
            "at_risk": at_risk,
            "breached": breached,
            "compliance_rate": round(compliance_rate, 2),
        }
