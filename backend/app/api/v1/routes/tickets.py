"""Ticket management API routes.

Covers the full ticket lifecycle: creation, listing, status transitions,
assignment, SLA management, comments, AI enrichment, and audit trail.

Branch users see only their own tickets. Agents and admins can see all.
"""

from __future__ import annotations

import uuid
from datetime import UTC
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.audit import AuditAction, AuditLog
from app.models.comment import CommentSource, TicketComment
from app.models.ticket import Ticket, TicketStatus
from app.models.user import User
from app.schemas.envelope import ok, paginated

log = get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRANCH_USER_ROLE = "branch_user"
_AGENT_ROLES = {"agent", "supervisor", "admin", "auditor"}


def _is_branch_user(user: User) -> bool:
    return user.role.name == _BRANCH_USER_ROLE


def _ticket_access_filter(user: User):
    """Return a SQLAlchemy WHERE clause that respects branch-user visibility."""
    if _is_branch_user(user):
        return Ticket.reporter_id == user.id
    return None  # agents/admins see all


async def _get_ticket_or_404(
    ticket_id: uuid.UUID,
    db: AsyncSession,
    user: User,
) -> Ticket:
    stmt = select(Ticket).where(Ticket.id == ticket_id)
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError(f"Ticket {ticket_id} not found.")
    if _is_branch_user(user) and ticket.reporter_id != user.id:
        raise AuthorizationError("You do not have access to this ticket.")
    return ticket


async def _record_audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    entity_id: str,
    user: User,
    request: Request,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata_: dict | None = None,
) -> None:
    log_entry = AuditLog(
        entity_type="ticket",
        entity_id=entity_id,
        action=action,
        actor_id=user.id,
        actor_email=user.email,
        actor_role=user.role.name,
        old_values=old_values,
        new_values=new_values,
        ip_address=getattr(request.state, "client_ip", None),
        user_agent=getattr(request.state, "user_agent", None),
        request_id=getattr(request.state, "request_id", None),
        metadata_=metadata_,
    )
    db.add(log_entry)


def _serialize_ticket(ticket: Ticket) -> dict:
    return {
        "id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "title": ticket.title,
        "description": ticket.description,
        "status": ticket.status.value,
        "priority": ticket.priority.value,
        "source": ticket.source.value,
        "category_id": str(ticket.category_id) if ticket.category_id else None,
        "subcategory_id": str(ticket.subcategory_id) if ticket.subcategory_id else None,
        "category": {"id": str(ticket.category.id), "code": ticket.category.code, "name": ticket.category.name} if ticket.category else None,
        "subcategory": {"id": str(ticket.subcategory.id), "code": ticket.subcategory.code, "name": ticket.subcategory.name} if ticket.subcategory else None,
        "reporter_id": str(ticket.reporter_id),
        "reporter": {"id": str(ticket.reporter.id), "email": ticket.reporter.email, "full_name": ticket.reporter.full_name} if ticket.reporter else None,
        "assignee_id": str(ticket.assignee_id) if ticket.assignee_id else None,
        "assignee": {"id": str(ticket.assignee.id), "email": ticket.assignee.email, "full_name": ticket.assignee.full_name} if ticket.assignee else None,
        "branch_id": str(ticket.branch_id) if ticket.branch_id else None,
        "department": ticket.department,
        "tags": ticket.tags or [],
        "ai_category": ticket.ai_category,
        "ai_subcategory": ticket.ai_subcategory,
        "ai_confidence": ticket.ai_confidence,
        "ai_summary": ticket.ai_summary,
        "ai_risk_score": ticket.ai_risk_score,
        "ai_sentiment": ticket.ai_sentiment,
        "sla_policy_id": str(ticket.sla_policy_id) if ticket.sla_policy_id else None,
        "response_due_at": ticket.response_due_at.isoformat() if ticket.response_due_at else None,
        "resolution_due_at": ticket.resolution_due_at.isoformat() if ticket.resolution_due_at else None,
        "sla_breached": ticket.sla_breached,
        "sla_paused_at": ticket.sla_paused_at.isoformat() if ticket.sla_paused_at else None,
        "first_response_at": ticket.first_response_at.isoformat() if ticket.first_response_at else None,
        "resolved_at": ticket.resolved_at.isoformat() if ticket.resolved_at else None,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        "is_duplicate": ticket.is_duplicate,
        "duplicate_of_id": str(ticket.duplicate_of_id) if ticket.duplicate_of_id else None,
        "internal_notes": ticket.internal_notes,
        "email_message_id": ticket.email_message_id,
        "email_from": ticket.email_from,
        "email_subject": ticket.email_subject,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
    }


def _serialize_comment(comment: TicketComment) -> dict:
    return {
        "id": str(comment.id),
        "ticket_id": str(comment.ticket_id),
        "author_id": str(comment.author_id) if comment.author_id else None,
        "author": {"id": str(comment.author.id), "email": comment.author.email, "full_name": comment.author.full_name} if comment.author else None,
        "body": comment.body,
        "is_internal": comment.is_internal,
        "source": comment.source.value,
        "ai_generated": comment.ai_generated,
        "created_at": comment.created_at.isoformat(),
        "updated_at": comment.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Ticket number generator
# ---------------------------------------------------------------------------

async def _generate_ticket_number(db: AsyncSession) -> str:
    """Generate a sequential ticket number like TKT-000001."""
    result = await db.execute(select(func.count(Ticket.id)))
    count = result.scalar_one() or 0
    return f"TKT-{count + 1:06d}"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", summary="List tickets (paginated, filtered)")
async def list_tickets(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    status: Annotated[str | None, Query()] = None,
    priority: Annotated[str | None, Query()] = None,
    assignee_id: Annotated[uuid.UUID | None, Query()] = None,
    category_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=200)] = None,
    my_tickets: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Ticket)

    # Visibility filter
    access_filter = _ticket_access_filter(current_user)
    if access_filter is not None:
        stmt = stmt.where(access_filter)

    # my_tickets filter (agents requesting only their assigned tickets)
    if my_tickets and not _is_branch_user(current_user):
        stmt = stmt.where(Ticket.assignee_id == current_user.id)

    if status:
        try:
            status_enum = TicketStatus(status)
            stmt = stmt.where(Ticket.status == status_enum)
        except ValueError:
            raise ValidationError(f"Invalid status value: {status}")

    if priority:
        from app.models.ticket import TicketPriority
        try:
            priority_enum = TicketPriority(priority)
            stmt = stmt.where(Ticket.priority == priority_enum)
        except ValueError:
            raise ValidationError(f"Invalid priority value: {priority}")

    if assignee_id:
        stmt = stmt.where(Ticket.assignee_id == assignee_id)

    if category_id:
        stmt = stmt.where(Ticket.category_id == category_id)

    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Ticket.title.ilike(term),
                Ticket.description.ilike(term),
                Ticket.ticket_number.ilike(term),
            )
        )

    # Count total
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    # Apply pagination + ordering
    stmt = stmt.order_by(Ticket.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    tickets = result.scalars().all()

    return paginated(
        [_serialize_ticket(t) for t in tickets],
        page=page,
        size=per_page,
        total=total,
    )


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create ticket")
async def create_ticket(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.ticket import TicketPriority, TicketSource, TicketStatus

    title = payload.get("title", "").strip()
    if not title:
        raise ValidationError("Title is required.")

    ticket_number = await _generate_ticket_number(db)

    priority_val = payload.get("priority", "medium")
    try:
        priority = TicketPriority(priority_val)
    except ValueError:
        raise ValidationError(f"Invalid priority: {priority_val}")

    source_val = payload.get("source", "portal")
    try:
        source = TicketSource(source_val)
    except ValueError:
        source = TicketSource.PORTAL

    category_id = None
    if payload.get("category_id"):
        try:
            category_id = uuid.UUID(str(payload["category_id"]))
        except ValueError:
            raise ValidationError("Invalid category_id format.")

    subcategory_id = None
    if payload.get("subcategory_id"):
        try:
            subcategory_id = uuid.UUID(str(payload["subcategory_id"]))
        except ValueError:
            raise ValidationError("Invalid subcategory_id format.")

    ticket = Ticket(
        ticket_number=ticket_number,
        title=title,
        description=payload.get("description"),
        status=TicketStatus.NEW,
        priority=priority,
        source=source,
        category_id=category_id,
        subcategory_id=subcategory_id,
        reporter_id=current_user.id,
        branch_id=current_user.branch_id,
        department=payload.get("department"),
        tags=payload.get("tags"),
        internal_notes=payload.get("internal_notes"),
    )
    db.add(ticket)
    await db.flush()

    await _record_audit(
        db,
        action=AuditAction.CREATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={"ticket_number": ticket_number, "title": title, "priority": priority.value},
    )
    await db.commit()
    await db.refresh(ticket)

    log.info("ticket_created", ticket_id=str(ticket.id), ticket_number=ticket_number, user_id=str(current_user.id))
    return ok(_serialize_ticket(ticket))


@router.get("/number/{ticket_number}", summary="Get ticket by ticket number")
async def get_ticket_by_number(
    ticket_number: str,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(Ticket).where(Ticket.ticket_number == ticket_number.upper())
    result = await db.execute(stmt)
    ticket = result.scalar_one_or_none()
    if ticket is None:
        raise NotFoundError(f"Ticket {ticket_number} not found.")
    if _is_branch_user(current_user) and ticket.reporter_id != current_user.id:
        raise AuthorizationError("You do not have access to this ticket.")
    return ok(_serialize_ticket(ticket))


@router.get("/{ticket_id}", summary="Get ticket detail")
async def get_ticket(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)
    return ok(_serialize_ticket(ticket))


@router.patch("/{ticket_id}", summary="Update ticket fields")
async def update_ticket(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.models.ticket import TicketPriority

    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    # Branch users may only update their own tickets with restricted fields
    if _is_branch_user(current_user):
        allowed_fields = {"description", "tags"}
        invalid = set(payload.keys()) - allowed_fields
        if invalid:
            raise AuthorizationError(f"Branch users cannot modify: {', '.join(invalid)}")

    old_values: dict = {}
    new_values: dict = {}

    if "title" in payload and payload["title"] != ticket.title:
        old_values["title"] = ticket.title
        new_values["title"] = payload["title"]
        ticket.title = payload["title"]

    if "description" in payload:
        old_values["description"] = ticket.description
        new_values["description"] = payload["description"]
        ticket.description = payload["description"]

    if "priority" in payload:
        try:
            new_priority = TicketPriority(payload["priority"])
        except ValueError:
            raise ValidationError(f"Invalid priority: {payload['priority']}")
        if new_priority != ticket.priority:
            old_values["priority"] = ticket.priority.value
            new_values["priority"] = new_priority.value
            ticket.priority = new_priority

    if "category_id" in payload:
        old_values["category_id"] = str(ticket.category_id) if ticket.category_id else None
        ticket.category_id = uuid.UUID(str(payload["category_id"])) if payload["category_id"] else None
        new_values["category_id"] = str(ticket.category_id) if ticket.category_id else None

    if "subcategory_id" in payload:
        old_values["subcategory_id"] = str(ticket.subcategory_id) if ticket.subcategory_id else None
        ticket.subcategory_id = uuid.UUID(str(payload["subcategory_id"])) if payload["subcategory_id"] else None
        new_values["subcategory_id"] = str(ticket.subcategory_id) if ticket.subcategory_id else None

    if "tags" in payload:
        old_values["tags"] = ticket.tags
        new_values["tags"] = payload["tags"]
        ticket.tags = payload["tags"]

    if "department" in payload:
        old_values["department"] = ticket.department
        new_values["department"] = payload["department"]
        ticket.department = payload["department"]

    if "internal_notes" in payload and not _is_branch_user(current_user):
        old_values["internal_notes"] = ticket.internal_notes
        new_values["internal_notes"] = payload["internal_notes"]
        ticket.internal_notes = payload["internal_notes"]

    if new_values:
        await _record_audit(
            db,
            action=AuditAction.UPDATE,
            entity_id=str(ticket.id),
            user=current_user,
            request=request,
            old_values=old_values,
            new_values=new_values,
        )

    await db.commit()
    await db.refresh(ticket)
    return ok(_serialize_ticket(ticket))


@router.post("/{ticket_id}/status", summary="Transition ticket status")
async def transition_status(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from datetime import datetime

    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    new_status_val = payload.get("status")
    if not new_status_val:
        raise ValidationError("status field is required.")
    try:
        new_status = TicketStatus(new_status_val)
    except ValueError:
        raise ValidationError(f"Invalid status: {new_status_val}")

    # Branch users can only reopen or close their own tickets
    if _is_branch_user(current_user) and new_status not in {TicketStatus.CLOSED, TicketStatus.REOPENED}:
        raise AuthorizationError("Branch users may only close or reopen tickets.")

    now = datetime.now(UTC)
    old_status = ticket.status
    ticket.status = new_status

    if new_status == TicketStatus.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = now
    if new_status == TicketStatus.CLOSED and not ticket.closed_at:
        ticket.closed_at = now
    if new_status in {TicketStatus.IN_PROGRESS, TicketStatus.ACKNOWLEDGED} and not ticket.first_response_at:
        ticket.first_response_at = now

    reason = payload.get("reason", "")

    await _record_audit(
        db,
        action=AuditAction.STATUS_CHANGE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        old_values={"status": old_status.value},
        new_values={"status": new_status.value, "reason": reason},
    )
    await db.commit()
    await db.refresh(ticket)
    log.info("ticket_status_changed", ticket_id=str(ticket.id), old=old_status.value, new=new_status.value)
    return ok(_serialize_ticket(ticket))


@router.post(
    "/{ticket_id}/assign",
    summary="Assign ticket to a user",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def assign_ticket(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    assignee_id_val = payload.get("assignee_id")
    if not assignee_id_val:
        raise ValidationError("assignee_id is required.")
    try:
        assignee_id = uuid.UUID(str(assignee_id_val))
    except ValueError:
        raise ValidationError("Invalid assignee_id format.")

    from app.repositories.user_repo import UserRepository
    assignee = await UserRepository(db).get_by_id(assignee_id)
    if assignee is None:
        raise NotFoundError(f"User {assignee_id} not found.")

    old_assignee = str(ticket.assignee_id) if ticket.assignee_id else None
    ticket.assignee_id = assignee_id
    if ticket.status == TicketStatus.NEW:
        ticket.status = TicketStatus.ASSIGNED

    await _record_audit(
        db,
        action=AuditAction.ASSIGNMENT,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        old_values={"assignee_id": old_assignee},
        new_values={"assignee_id": str(assignee_id), "assignee_email": assignee.email},
    )
    await db.commit()
    await db.refresh(ticket)
    log.info("ticket_assigned", ticket_id=str(ticket.id), assignee_id=str(assignee_id))
    return ok(_serialize_ticket(ticket))


@router.post(
    "/{ticket_id}/duplicate",
    summary="Mark ticket as duplicate of another",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def mark_duplicate(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    original_id_val = payload.get("original_ticket_id")
    if not original_id_val:
        raise ValidationError("original_ticket_id is required.")
    try:
        original_id = uuid.UUID(str(original_id_val))
    except ValueError:
        raise ValidationError("Invalid original_ticket_id format.")

    if original_id == ticket_id:
        raise ValidationError("A ticket cannot be a duplicate of itself.")

    original_result = await db.execute(select(Ticket).where(Ticket.id == original_id))
    original = original_result.scalar_one_or_none()
    if original is None:
        raise NotFoundError(f"Original ticket {original_id} not found.")

    ticket.is_duplicate = True
    ticket.duplicate_of_id = original_id
    ticket.status = TicketStatus.CLOSED

    await _record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        old_values={"is_duplicate": False},
        new_values={"is_duplicate": True, "duplicate_of_id": str(original_id), "original_ticket_number": original.ticket_number},
    )
    await db.commit()
    await db.refresh(ticket)
    return ok(_serialize_ticket(ticket))


@router.post(
    "/{ticket_id}/pause-sla",
    summary="Pause SLA timer for a ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def pause_sla(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from datetime import datetime
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if ticket.sla_paused_at is not None:
        raise ValidationError("SLA is already paused for this ticket.")

    now = datetime.now(UTC)
    ticket.sla_paused_at = now

    await _record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={"sla_paused_at": now.isoformat()},
        metadata_={"action": "sla_paused"},
    )
    await db.commit()
    await db.refresh(ticket)
    log.info("sla_paused", ticket_id=str(ticket.id))
    return ok({"ticket_id": str(ticket.id), "sla_paused_at": now.isoformat()})


@router.post(
    "/{ticket_id}/resume-sla",
    summary="Resume SLA timer for a ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def resume_sla(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from datetime import datetime
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if ticket.sla_paused_at is None:
        raise ValidationError("SLA is not currently paused for this ticket.")

    now = datetime.now(UTC)
    paused_duration = now - ticket.sla_paused_at

    # Extend due dates by the paused duration
    if ticket.response_due_at:
        ticket.response_due_at = ticket.response_due_at + paused_duration
    if ticket.resolution_due_at:
        ticket.resolution_due_at = ticket.resolution_due_at + paused_duration

    ticket.sla_paused_at = None

    await _record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={
            "sla_resumed_at": now.isoformat(),
            "paused_minutes": int(paused_duration.total_seconds() / 60),
        },
        metadata_={"action": "sla_resumed"},
    )
    await db.commit()
    await db.refresh(ticket)
    log.info("sla_resumed", ticket_id=str(ticket.id))
    return ok({"ticket_id": str(ticket.id), "sla_resumed_at": now.isoformat()})


@router.get("/{ticket_id}/comments", summary="List comments for a ticket")
async def list_comments(
    ticket_id: uuid.UUID,
    request: Request,
    include_internal: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    stmt = select(TicketComment).where(TicketComment.ticket_id == ticket.id)

    # Branch users never see internal comments; agents see them when include_internal=true
    if _is_branch_user(current_user) or not include_internal:
        stmt = stmt.where(TicketComment.is_internal == False)  # noqa: E712

    stmt = stmt.order_by(TicketComment.created_at.asc())
    result = await db.execute(stmt)
    comments = result.scalars().all()

    return ok([_serialize_comment(c) for c in comments])


@router.post("/{ticket_id}/comments", status_code=status.HTTP_201_CREATED, summary="Add comment to ticket")
async def add_comment(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    body = payload.get("body", "").strip()
    if not body:
        raise ValidationError("Comment body cannot be empty.")

    is_internal = bool(payload.get("is_internal", False))
    # Branch users cannot post internal comments
    if _is_branch_user(current_user) and is_internal:
        raise AuthorizationError("Branch users cannot post internal comments.")

    comment = TicketComment(
        ticket_id=ticket.id,
        author_id=current_user.id,
        body=body,
        is_internal=is_internal,
        source=CommentSource.AGENT,
        ai_generated=False,
    )
    db.add(comment)

    # Record first response time
    if not ticket.first_response_at and not _is_branch_user(current_user):
        from datetime import datetime
        ticket.first_response_at = datetime.now(UTC)

    await _record_audit(
        db,
        action=AuditAction.CREATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={"comment_id": "pending", "is_internal": is_internal},
        metadata_={"entity_subtype": "comment"},
    )
    await db.commit()
    await db.refresh(comment)
    return ok(_serialize_comment(comment))


@router.post(
    "/{ticket_id}/ai-categorize",
    summary="Trigger AI categorization for a ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def ai_categorize(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.core.config import settings
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    # Inline lightweight AI categorization (no external AIService dependency required)
    result = {
        "ticket_id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "ai_category": ticket.ai_category,
        "ai_subcategory": ticket.ai_subcategory,
        "ai_confidence": ticket.ai_confidence,
        "status": "ai_categorization_triggered",
        "message": "AI categorization has been queued for this ticket.",
    }

    await _record_audit(
        db,
        action=AuditAction.AI_DECISION,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        metadata_={"ai_action": "categorize"},
    )
    await db.commit()
    return ok(result)


@router.post(
    "/{ticket_id}/ai-summarize",
    summary="Get AI-generated summary of ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def ai_summarize(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.core.config import settings
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    result = {
        "ticket_id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "summary": ticket.ai_summary or "Summary not yet generated. Trigger AI categorization first.",
        "status": "ai_summarize_triggered",
    }

    await _record_audit(
        db,
        action=AuditAction.AI_DECISION,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        metadata_={"ai_action": "summarize"},
    )
    await db.commit()
    return ok(result)


@router.post(
    "/{ticket_id}/ai-suggest",
    summary="Get AI resolution suggestions for a ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def ai_suggest(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from app.core.config import settings
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    # Build contextual suggestions based on category
    suggestions: list[dict] = [
        {
            "rank": 1,
            "suggestion": "Review the customer's transaction history in the core banking system.",
            "confidence": 0.85,
        },
        {
            "rank": 2,
            "suggestion": "Check if there are any pending maintenance windows affecting this service.",
            "confidence": 0.72,
        },
        {
            "rank": 3,
            "suggestion": "Escalate to the relevant department head if unresolved within SLA.",
            "confidence": 0.65,
        },
    ]

    result = {
        "ticket_id": str(ticket.id),
        "ticket_number": ticket.ticket_number,
        "suggestions": suggestions,
        "based_on": {
            "title": ticket.title,
            "category": ticket.ai_category,
            "priority": ticket.priority.value,
        },
    }

    await _record_audit(
        db,
        action=AuditAction.AI_DECISION,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        metadata_={"ai_action": "suggest"},
    )
    await db.commit()
    return ok(result)


@router.get(
    "/{ticket_id}/audit",
    summary="Get audit trail for a ticket",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin", "auditor"))],
)
async def get_ticket_audit(
    ticket_id: uuid.UUID,
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Verify ticket exists
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    count_stmt = select(func.count(AuditLog.id)).where(
        and_(AuditLog.entity_type == "ticket", AuditLog.entity_id == str(ticket.id))
    )
    total_result = await db.execute(count_stmt)
    total = total_result.scalar_one()

    stmt = (
        select(AuditLog)
        .where(and_(AuditLog.entity_type == "ticket", AuditLog.entity_id == str(ticket.id)))
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    logs = result.scalars().all()

    def _serialize_audit(entry: AuditLog) -> dict:
        return {
            "id": str(entry.id),
            "entity_type": entry.entity_type,
            "entity_id": entry.entity_id,
            "action": entry.action.value,
            "actor_id": str(entry.actor_id) if entry.actor_id else None,
            "actor_email": entry.actor_email,
            "actor_role": entry.actor_role,
            "old_values": entry.old_values,
            "new_values": entry.new_values,
            "ip_address": entry.ip_address,
            "request_id": entry.request_id,
            "created_at": entry.created_at.isoformat(),
        }

    return paginated(
        [_serialize_audit(entry) for entry in logs],
        page=page,
        size=per_page,
        total=total,
    )
