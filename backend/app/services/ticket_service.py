"""Ticket service — all business logic for the ticket lifecycle.

Responsibilities:
- Ticket number generation (TKT-YYYYMMDD-NNNNN, sequential per day)
- Full CRUD with audit logging
- FSM-based status transitions
- Assignment logic
- Comment management
- Duplicate marking
- SLA delegation to SLAService
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit import AuditAction
from app.models.comment import CommentSource, TicketComment
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketSource,
    TicketStatus,
)
from app.schemas.ticket import CommentCreate, TicketCreate, TicketUpdate
from app.services.audit_service import AuditService
from app.services.sla_service import SLAService

log = get_logger(__name__)

# ---------------------------------------------------------------------------
# FSM: allowed transitions per source status
# ---------------------------------------------------------------------------

VALID_TRANSITIONS: dict[TicketStatus, list[TicketStatus]] = {
    TicketStatus.NEW: [
        TicketStatus.ACKNOWLEDGED,
        TicketStatus.ASSIGNED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.ACKNOWLEDGED: [
        TicketStatus.ASSIGNED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.ASSIGNED: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.ON_HOLD,
        TicketStatus.ESCALATED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.IN_PROGRESS: [
        TicketStatus.ON_HOLD,
        TicketStatus.ESCALATED,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.ON_HOLD: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.ESCALATED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.ESCALATED: [
        TicketStatus.IN_PROGRESS,
        TicketStatus.RESOLVED,
        TicketStatus.CLOSED,
    ],
    TicketStatus.RESOLVED: [
        TicketStatus.CLOSED,
        TicketStatus.REOPENED,
    ],
    TicketStatus.CLOSED: [
        TicketStatus.REOPENED,
    ],
    TicketStatus.REOPENED: [
        TicketStatus.ASSIGNED,
        TicketStatus.IN_PROGRESS,
    ],
}


class TicketService:
    def __init__(
        self,
        db: AsyncSession,
        actor_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        self.db = db
        self.actor_id = actor_id
        self.request_id = request_id
        self._audit = AuditService(db)
        self._sla = SLAService(db)

    # ------------------------------------------------------------------
    # Ticket number generation
    # ------------------------------------------------------------------

    async def generate_ticket_number(self) -> str:
        """Generate TKT-YYYYMMDD-NNNNN, sequential within the calendar day."""
        today = datetime.now(timezone.utc).strftime("%Y%m%d")
        prefix = f"TKT-{today}-"

        stmt = (
            select(func.count())
            .select_from(Ticket)
            .where(Ticket.ticket_number.like(f"{prefix}%"))
        )
        count: int = (await self.db.execute(stmt)).scalar_one()
        sequence = count + 1
        return f"{prefix}{sequence:05d}"

    # ------------------------------------------------------------------
    # Create
    # ------------------------------------------------------------------

    async def create_ticket(
        self,
        data: TicketCreate,
        reporter_id: uuid.UUID,
        *,
        source: TicketSource = TicketSource.PORTAL,
    ) -> Ticket:
        """Create a ticket, assign a number, log audit, and apply SLA."""
        ticket_number = await self.generate_ticket_number()

        ticket = Ticket(
            ticket_number=ticket_number,
            title=data.title,
            description=data.description,
            priority=data.priority.value if isinstance(data.priority, TicketPriority) else data.priority,
            source=data.source.value if isinstance(data.source, TicketSource) else source.value,
            category_id=data.category_id,
            subcategory_id=data.subcategory_id,
            reporter_id=reporter_id,
            tags=data.tags,
            status=TicketStatus.NEW.value,
        )
        self.db.add(ticket)
        await self.db.flush()  # obtain ticket.id before SLA

        await self._sla.apply_to_ticket(ticket)

        await self._audit.log(
            entity_type="ticket",
            entity_id=str(ticket.id),
            action=AuditAction.CREATE,
            actor_id=self.actor_id,
            new_values={
                "ticket_number": ticket_number,
                "title": data.title,
                "priority": ticket.priority,
                "source": ticket.source,
                "reporter_id": str(reporter_id),
            },
            request_id=self.request_id,
        )

        await self.db.commit()
        await self.db.refresh(ticket)
        log.info("ticket.created", ticket_id=str(ticket.id), ticket_number=ticket_number)
        return ticket

    # ------------------------------------------------------------------
    # Update
    # ------------------------------------------------------------------

    async def update_ticket(
        self,
        ticket_id: uuid.UUID,
        data: TicketUpdate,
        actor_id: uuid.UUID,
    ) -> Ticket:
        """Update mutable ticket fields, recording changed values in audit log."""
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket {ticket_id} not found.")

        old_values: dict = {}
        new_values: dict = {}

        update_map = data.model_dump(exclude_unset=True)

        for field, value in update_map.items():
            current = getattr(ticket, field, None)
            if field == "priority" and isinstance(value, TicketPriority):
                value = value.value
            if field == "status" and isinstance(value, TicketStatus):
                value = value.value
            if current != value:
                old_values[field] = str(current) if current is not None else None
                new_values[field] = str(value) if value is not None else None
                setattr(ticket, field, value)

        if old_values:
            await self.db.flush()
            await self._audit.log(
                entity_type="ticket",
                entity_id=str(ticket_id),
                action=AuditAction.UPDATE,
                actor_id=str(actor_id),
                old_values=old_values,
                new_values=new_values,
                request_id=self.request_id,
            )
            await self.db.commit()
            await self.db.refresh(ticket)

        return ticket

    # ------------------------------------------------------------------
    # Status transition (FSM)
    # ------------------------------------------------------------------

    async def transition_status(
        self,
        ticket_id: uuid.UUID,
        new_status: TicketStatus,
        actor_id: uuid.UUID,
        reason: str | None = None,
    ) -> Ticket:
        """Apply a validated FSM status transition with full audit logging."""
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket {ticket_id} not found.")

        current_status_str = (
            ticket.status if isinstance(ticket.status, str) else ticket.status.value
        )
        current_status = TicketStatus(current_status_str)

        allowed = VALID_TRANSITIONS.get(current_status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot transition from '{current_status.value}' to '{new_status.value}'. "
                f"Allowed: {[s.value for s in allowed]}"
            )

        now = datetime.now(timezone.utc)
        old_status_value = current_status.value
        ticket.status = new_status.value

        # Update lifecycle timestamps
        if new_status == TicketStatus.RESOLVED:
            ticket.resolved_at = now
        elif new_status == TicketStatus.CLOSED:
            ticket.closed_at = now
        elif new_status in (TicketStatus.REOPENED, TicketStatus.IN_PROGRESS):
            ticket.resolved_at = None
            ticket.closed_at = None

        await self.db.flush()
        await self._audit.log(
            entity_type="ticket",
            entity_id=str(ticket_id),
            action=AuditAction.STATUS_CHANGE,
            actor_id=str(actor_id),
            old_values={"status": old_status_value},
            new_values={"status": new_status.value, "reason": reason},
            request_id=self.request_id,
        )
        await self.db.commit()
        await self.db.refresh(ticket)
        log.info(
            "ticket.status_changed",
            ticket_id=str(ticket_id),
            from_status=old_status_value,
            to_status=new_status.value,
        )
        return ticket

    # ------------------------------------------------------------------
    # Assignment
    # ------------------------------------------------------------------

    async def assign_ticket(
        self,
        ticket_id: uuid.UUID,
        assignee_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> Ticket:
        """Assign a ticket to an agent, transitioning to ASSIGNED if in NEW/ACK."""
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket {ticket_id} not found.")

        old_assignee = str(ticket.assignee_id) if ticket.assignee_id else None
        ticket.assignee_id = assignee_id

        current_status_str = (
            ticket.status if isinstance(ticket.status, str) else ticket.status.value
        )
        current_status = TicketStatus(current_status_str)
        if current_status in (TicketStatus.NEW, TicketStatus.ACKNOWLEDGED):
            ticket.status = TicketStatus.ASSIGNED.value

        await self.db.flush()
        await self._audit.log(
            entity_type="ticket",
            entity_id=str(ticket_id),
            action=AuditAction.ASSIGNMENT,
            actor_id=str(actor_id),
            old_values={"assignee_id": old_assignee},
            new_values={"assignee_id": str(assignee_id), "status": ticket.status},
            request_id=self.request_id,
        )
        await self.db.commit()
        await self.db.refresh(ticket)
        return ticket

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_ticket(self, ticket_id: uuid.UUID) -> Ticket | None:
        """Load a single ticket by primary key."""
        return await self.db.get(Ticket, ticket_id)

    async def list_tickets(
        self,
        *,
        page: int = 1,
        per_page: int = 25,
        status: str | None = None,
        priority: str | None = None,
        assignee_id: uuid.UUID | None = None,
        reporter_id: uuid.UUID | None = None,
        category_id: uuid.UUID | None = None,
        search: str | None = None,
    ) -> tuple[list[Ticket], int]:
        """Return a paginated, filtered list of tickets and the total count."""
        stmt = select(Ticket)

        if status:
            stmt = stmt.where(Ticket.status == status)
        if priority:
            stmt = stmt.where(Ticket.priority == priority)
        if assignee_id is not None:
            stmt = stmt.where(Ticket.assignee_id == assignee_id)
        if reporter_id is not None:
            stmt = stmt.where(Ticket.reporter_id == reporter_id)
        if category_id is not None:
            stmt = stmt.where(Ticket.category_id == category_id)
        if search:
            pattern = f"%{search}%"
            stmt = stmt.where(
                or_(
                    Ticket.title.ilike(pattern),
                    Ticket.ticket_number.ilike(pattern),
                    Ticket.description.ilike(pattern),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await self.db.execute(count_stmt)).scalar_one()

        offset = (page - 1) * per_page
        stmt = stmt.order_by(Ticket.created_at.desc()).offset(offset).limit(per_page)
        rows = list((await self.db.execute(stmt)).scalars().all())
        return rows, total

    # ------------------------------------------------------------------
    # Comments
    # ------------------------------------------------------------------

    async def add_comment(
        self,
        ticket_id: uuid.UUID,
        data: CommentCreate,
        author_id: uuid.UUID | None = None,
        *,
        source: CommentSource = CommentSource.AGENT,
    ) -> TicketComment:
        """Add a comment to a ticket; marks first_response_at on first non-internal comment."""
        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket {ticket_id} not found.")

        comment = TicketComment(
            ticket_id=ticket_id,
            author_id=author_id,
            body=data.body,
            is_internal=data.is_internal,
            source=source.value if isinstance(source, CommentSource) else source,
        )
        self.db.add(comment)

        # Record first external response timestamp
        if not data.is_internal and ticket.first_response_at is None and author_id is not None:
            ticket.first_response_at = datetime.now(timezone.utc)

            # Update SLATracking
            from sqlalchemy import select as _select
            from app.models.sla import SLATracking
            track_stmt = _select(SLATracking).where(SLATracking.ticket_id == ticket_id)
            tracking = (await self.db.execute(track_stmt)).scalar_one_or_none()
            if tracking and tracking.first_response_at is None:
                tracking.first_response_at = ticket.first_response_at

        await self.db.flush()
        await self._audit.log(
            entity_type="ticket_comment",
            entity_id=str(comment.id),
            action=AuditAction.CREATE,
            actor_id=str(author_id) if author_id else self.actor_id,
            new_values={
                "ticket_id": str(ticket_id),
                "is_internal": data.is_internal,
                "source": str(source.value if isinstance(source, CommentSource) else source),
            },
            request_id=self.request_id,
        )
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    # ------------------------------------------------------------------
    # Duplicate management
    # ------------------------------------------------------------------

    async def mark_duplicate(
        self,
        ticket_id: uuid.UUID,
        original_id: uuid.UUID,
        actor_id: uuid.UUID,
    ) -> Ticket:
        """Mark ticket_id as a duplicate of original_id and close it."""
        if ticket_id == original_id:
            raise ValidationError("A ticket cannot be a duplicate of itself.")

        ticket = await self.get_ticket(ticket_id)
        if ticket is None:
            raise NotFoundError(f"Ticket {ticket_id} not found.")

        original = await self.get_ticket(original_id)
        if original is None:
            raise NotFoundError(f"Original ticket {original_id} not found.")

        ticket.duplicate_of_id = original_id
        ticket.is_duplicate = True
        ticket.status = TicketStatus.CLOSED.value
        ticket.closed_at = datetime.now(timezone.utc)

        await self.db.flush()
        await self._audit.log(
            entity_type="ticket",
            entity_id=str(ticket_id),
            action=AuditAction.UPDATE,
            actor_id=str(actor_id),
            old_values={"is_duplicate": False, "duplicate_of_id": None},
            new_values={"is_duplicate": True, "duplicate_of_id": str(original_id)},
            request_id=self.request_id,
        )
        await self.db.commit()
        await self.db.refresh(ticket)
        log.info("ticket.marked_duplicate", ticket_id=str(ticket_id), original_id=str(original_id))
        return ticket

    # ------------------------------------------------------------------
    # Categories
    # ------------------------------------------------------------------

    async def get_categories(self) -> list[TicketCategory]:
        """Return all active ticket categories."""
        stmt = select(TicketCategory).where(TicketCategory.is_active.is_(True))
        return list((await self.db.execute(stmt)).scalars().all())

    # ------------------------------------------------------------------
    # SLA delegation helpers (kept for backward compat / convenience)
    # ------------------------------------------------------------------

    async def apply_sla_policy(self, ticket: Ticket) -> None:
        """Delegate SLA application to SLAService."""
        await self._sla.apply_to_ticket(ticket)

    async def pause_sla(self, ticket_id: uuid.UUID) -> None:
        """Pause SLA for the given ticket."""
        await self._sla.pause_sla(ticket_id)

    async def resume_sla(self, ticket_id: uuid.UUID) -> None:
        """Resume SLA for the given ticket."""
        await self._sla.resume_sla(ticket_id)
