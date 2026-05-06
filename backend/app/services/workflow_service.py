"""Ticket workflow service.

Centralises every state mutation:
  - status transitions (validated against ALLOWED_TRANSITIONS)
  - assignment (writes to ticket_assignments and updates ticket fields)
  - first-response timestamp on first agent comment
  - resolved_at / closed_at / reopened_count bookkeeping

Routes never mutate Ticket fields directly — they call into this service.
That makes the audit story (P6) trivial: one chokepoint to instrument.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.rbac import Role
from app.models.enums import ALLOWED_TRANSITIONS, TicketStatus
from app.models.ticket import Ticket
from app.models.ticket_history import TicketAssignment, TicketComment
from app.models.user import User
from app.repositories.ticket_history_repo import (
    TicketAssignmentRepository,
    TicketCommentRepository,
)
from app.repositories.ticket_repo import TicketRepository
from app.services.audit_service import AuditService
from app.services.escalation_service import EscalationService
from app.services.notification_service import (
    NotificationChannel,
    NotificationService,
    NotificationType,
)
from app.services.sla_engine import SLAEngine


class WorkflowService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.tickets = TicketRepository(db)
        self.assignments = TicketAssignmentRepository(db)
        self.comments = TicketCommentRepository(db)
        self.sla = SLAEngine(db)
        self.notifications = NotificationService(db)
        self.escalations = EscalationService(db)
        self.audit = AuditService(db)

    async def _log_status_change(self, actor: User, t: Ticket, prev: str, action: str) -> None:
        await self.audit.log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action=action,
            old_value={"status": prev},
            new_value={"status": t.status, "ticket_no": t.ticket_no},
        )

    # ---- helpers ---------------------------------------------------------

    async def _load_for(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self.tickets.get(ticket_id)
        if t is None:
            raise NotFoundError("Ticket not found.")
        if actor.role.name == Role.BRANCH_USER.value and t.branch_id != actor.branch_id:
            raise NotFoundError("Ticket not found.")
        return t

    def _assert_transition(self, current: str, target: TicketStatus) -> None:
        try:
            cur = TicketStatus(current)
        except ValueError as e:
            raise ValidationError("Unknown current status.") from e
        if target not in ALLOWED_TRANSITIONS[cur]:
            raise ConflictError(
                f"Cannot transition from {cur.value} to {target.value}.",
                details={"from": cur.value, "to": target.value},
            )

    # ---- transitions -----------------------------------------------------

    async def acknowledge(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.ACKNOWLEDGED)
        t.status = TicketStatus.ACKNOWLEDGED.value
        await self._log_status_change(actor, t, prev, "ticket.acknowledged")
        return t

    async def assign(
        self,
        actor: User,
        ticket_id: uuid.UUID,
        *,
        user_id: uuid.UUID | None,
        team_id: uuid.UUID | None,
        reason: str = "",
    ) -> Ticket:
        if user_id is None and team_id is None:
            raise ValidationError("Provide assigned user, team, or both.")
        t = await self._load_for(actor, ticket_id)

        # Allowed from new/acknowledged/escalated/reopened (and re-assignment from
        # in_progress/on_hold which already have an assignee).
        if t.status not in {
            TicketStatus.NEW.value,
            TicketStatus.ACKNOWLEDGED.value,
            TicketStatus.ASSIGNED.value,
            TicketStatus.ESCALATED.value,
            TicketStatus.REOPENED.value,
            TicketStatus.IN_PROGRESS.value,
            TicketStatus.ON_HOLD.value,
        }:
            raise ConflictError("Ticket cannot be (re)assigned in its current state.")

        await self.assignments.close_open_for(t.id)
        await self.assignments.add(
            TicketAssignment(
                ticket_id=t.id,
                assigned_to_user_id=user_id,
                assigned_to_team_id=team_id,
                assigned_by=actor.id,
                reason=reason[:255],
            )
        )
        t.assigned_user_id = user_id
        t.assigned_team_id = team_id
        if t.status in {TicketStatus.NEW.value, TicketStatus.ACKNOWLEDGED.value, TicketStatus.REOPENED.value}:
            t.status = TicketStatus.ASSIGNED.value

        if user_id is not None:
            await self.notifications.dispatch(
                user_ids=[user_id],
                type_=NotificationType.TICKET_ASSIGNED,
                subject=f"Ticket {t.ticket_no} assigned to you",
                body=f"{t.title}\n\nReason: {reason or '—'}",
                payload={"ticket_id": str(t.id), "ticket_no": t.ticket_no},
                channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
            )
        await self.audit.log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action="ticket.assigned",
            new_value={
                "user_id": str(user_id) if user_id else None,
                "team_id": str(team_id) if team_id else None,
                "reason": reason,
                "status": t.status,
            },
        )
        return t

    async def start(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        was_on_hold = t.status == TicketStatus.ON_HOLD.value
        self._assert_transition(t.status, TicketStatus.IN_PROGRESS)
        t.status = TicketStatus.IN_PROGRESS.value
        if was_on_hold:
            await self.sla.on_resumed(t)
        await self._log_status_change(actor, t, prev, "ticket.started")
        return t

    async def hold(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.ON_HOLD)
        t.status = TicketStatus.ON_HOLD.value
        await self.sla.on_paused(t)
        await self._log_status_change(actor, t, prev, "ticket.held")
        return t

    async def escalate(self, actor: User, ticket_id: uuid.UUID, *, reason: str = "") -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.ESCALATED)
        t.status = TicketStatus.ESCALATED.value
        if reason:
            await self.comments.add(
                TicketComment(
                    ticket_id=t.id, author_id=actor.id, body=f"[Escalated] {reason}", is_internal=True
                )
            )
        await self.escalations.raise_manual(ticket_id=t.id, triggered_by=actor, reason=reason)
        await self.audit.log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action="ticket.escalated",
            old_value={"status": prev},
            new_value={"status": t.status, "reason": reason},
        )
        return t

    async def resolve(self, actor: User, ticket_id: uuid.UUID, *, notes: str = "") -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.RESOLVED)
        t.status = TicketStatus.RESOLVED.value
        t.resolved_at = datetime.now(timezone.utc)
        if notes:
            await self.comments.add(
                TicketComment(
                    ticket_id=t.id, author_id=actor.id, body=f"[Resolution] {notes}", is_internal=False
                )
            )
        await self.notifications.dispatch(
            user_ids=[t.raised_by],
            type_=NotificationType.TICKET_RESOLVED,
            subject=f"Ticket {t.ticket_no} resolved",
            body=notes or "Your ticket has been resolved. Please confirm or reopen.",
            payload={"ticket_id": str(t.id), "ticket_no": t.ticket_no},
            channels=[NotificationChannel.IN_APP, NotificationChannel.EMAIL],
        )
        await self.audit.log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action="ticket.resolved",
            old_value={"status": prev},
            new_value={"status": t.status, "notes": notes},
        )
        return t

    async def close(self, actor: User, ticket_id: uuid.UUID) -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.CLOSED)
        t.status = TicketStatus.CLOSED.value
        t.closed_at = datetime.now(timezone.utc)
        await self._log_status_change(actor, t, prev, "ticket.closed")
        return t

    async def reopen(self, actor: User, ticket_id: uuid.UUID, *, reason: str = "") -> Ticket:
        t = await self._load_for(actor, ticket_id)
        prev = t.status
        self._assert_transition(t.status, TicketStatus.REOPENED)
        t.status = TicketStatus.REOPENED.value
        t.reopened_count += 1
        t.resolved_at = None
        t.closed_at = None
        await self.sla.on_reopened(t)
        if reason:
            await self.comments.add(
                TicketComment(
                    ticket_id=t.id, author_id=actor.id, body=f"[Reopened] {reason}", is_internal=False
                )
            )
        await self.audit.log(
            actor=actor,
            entity_type="ticket",
            entity_id=t.id,
            action="ticket.reopened",
            old_value={"status": prev},
            new_value={"status": t.status, "reopened_count": t.reopened_count, "reason": reason},
        )
        return t

    # ---- comments --------------------------------------------------------

    async def add_comment(
        self, actor: User, ticket_id: uuid.UUID, *, body: str, is_internal: bool
    ) -> TicketComment:
        t = await self._load_for(actor, ticket_id)

        # Branch users can never post internal comments.
        if actor.role.name == Role.BRANCH_USER.value and is_internal:
            raise ValidationError("Branch users cannot post internal comments.")

        # First-response time: first comment by an agent / supervisor / admin.
        if (
            t.first_response_at is None
            and actor.role.name in {Role.AGENT.value, Role.SUPERVISOR.value, Role.ADMIN.value}
            and not is_internal
        ):
            t.first_response_at = datetime.now(timezone.utc)

        c = TicketComment(
            ticket_id=t.id, author_id=actor.id, body=body.strip(), is_internal=is_internal
        )
        await self.comments.add(c)
        await self.audit.log(
            actor=actor,
            entity_type="ticket_comment",
            entity_id=c.id,
            action="comment.posted",
            new_value={
                "ticket_id": str(t.id),
                "is_internal": is_internal,
                "length": len(c.body),
            },
        )
        return c
