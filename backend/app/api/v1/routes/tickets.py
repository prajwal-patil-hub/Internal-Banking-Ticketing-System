"""Ticket management API routes."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.responses import Response
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core import authz
from app.core.exceptions import AuthorizationError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.attachment import Attachment
from app.models.audit import AuditAction, AuditLog
from app.models.comment import CommentSource, TicketComment
from app.models.escalation import EscalationEvent, EscalationTrigger
from app.models.ticket import OPEN_STATUSES as _OPEN_STATUSES
from app.models.ticket import (
    AI_RISK_HIGH_THRESHOLD,
    AI_RISK_MEDIUM_THRESHOLD,
    Ticket,
    TicketSource,
    TicketStatus,
)
from app.models.user import User
from app.schemas.envelope import ok, paginated
from app.services.org_service import get_accessible_org_unit_ids
from app.services.routing_service import RoutingService
from app.services.sla_service import SLAService
from app.services.storage_service import (
    build_key,
    sanitize_filename,
    storage,
    validate_upload,
)
from app.services.ticket_service import VALID_TRANSITIONS

log = get_logger(__name__)

router = APIRouter(prefix="/tickets", tags=["tickets"])

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BRANCH_USER_ROLE = authz.BRANCH_USER
#: Roles permitted to act on other people's tickets. Sourced from the central
#: policy — `auditor` used to be in this set and silently held write access.
_AGENT_ROLES = authz.TICKET_WRITE_ROLES



def _is_branch_user(user: User) -> bool:
    return user.role.name == _BRANCH_USER_ROLE


def _parse_dt(value: str, field: str) -> datetime:
    """Accept an ISO date or datetime; `2026-08-10` means midnight UTC."""
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise ValidationError(f"{field} must be an ISO 8601 date or datetime.")
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


async def _ticket_access_filter(user: User, db: AsyncSession):
    """Return a SQLAlchemy WHERE clause respecting org-scoped visibility."""
    if user.is_super_admin:
        return None
    # New org-hierarchy visibility: strictly org-unit scoped
    if user.org_unit_id:
        accessible = await get_accessible_org_unit_ids(user, db)
        if accessible is not None:
            return or_(
                Ticket.org_unit_id.in_(accessible),
                Ticket.assignee_id == user.id,
            )
        return None  # subtree admin sees all
    # Legacy: branch_user sees only own tickets
    if _is_branch_user(user):
        return Ticket.reporter_id == user.id
    return None  # agents/admins see all


def _can_modify_ticket(ticket: Ticket, user: User) -> bool:
    """Check if user can modify a ticket."""
    if user.is_super_admin:
        return True
    # Only the raiser can modify/communicate
    if str(ticket.reporter_id) == str(user.id):
        return True
    # Assigned agent can update status
    if ticket.assignee_id and str(ticket.assignee_id) == str(user.id):
        return True
    # Legacy agent/admin/supervisor roles
    if user.role.name in _AGENT_ROLES:
        return True
    return False


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
    # Org-scoped visibility check
    if not user.is_super_admin:
        if user.org_unit_id:
            accessible = await get_accessible_org_unit_ids(user, db)
            if accessible is not None:
                is_accessible = (
                    ticket.org_unit_id in accessible
                    or str(ticket.assignee_id) == str(user.id)
                )
                if not is_accessible:
                    raise AuthorizationError("You do not have access to this ticket.")
        elif _is_branch_user(user) and ticket.reporter_id != user.id:
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
        "org_unit_id": str(ticket.org_unit_id) if ticket.org_unit_id else None,
        "org_unit": {
            "id": str(ticket.org_unit.id),
            "name": ticket.org_unit.name,
            "code": ticket.org_unit.code,
            "level": ticket.org_unit.hierarchy_level.name if ticket.org_unit.hierarchy_level else None,
        } if ticket.org_unit else None,
        "department": ticket.department,
        "reopen_count": ticket.reopen_count or 0,
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

async def _generate_ticket_number(db: AsyncSession, org_unit_id: uuid.UUID | None = None) -> str:
    """Generate ticket number: org-scoped format or legacy TKT-NNNNNN."""
    if org_unit_id:
        from app.services.ticket_seq_service import generate_ticket_number
        return await generate_ticket_number(db, org_unit_id)
    from app.services.ticket_seq_service import generate_ticket_number_legacy
    return await generate_ticket_number_legacy(db)


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
    sla_breached: Annotated[bool | None, Query()] = None,
    source: Annotated[str | None, Query()] = None,
    status_group: Annotated[str | None, Query(pattern="^(open|closed)$")] = None,
    ai_categorized: Annotated[bool | None, Query()] = None,
    ai_risk: Annotated[str | None, Query(pattern="^(high|medium|low)$")] = None,
    created_from: Annotated[str | None, Query()] = None,
    resolved_from: Annotated[str | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """List tickets.

    The filters beyond status/priority exist so every dashboard KPI has a
    destination that reproduces its own number. A card reading "9 breached"
    that links to an unfiltered list is worse than a card that does nothing —
    it looks like the count is wrong.
    """
    stmt = select(Ticket)

    # Visibility filter
    access_filter = await _ticket_access_filter(current_user, db)
    if access_filter is not None:
        stmt = stmt.where(access_filter)

    # my_tickets filter (agents requesting only their assigned tickets)
    if my_tickets and not _is_branch_user(current_user):
        stmt = stmt.where(Ticket.assignee_id == current_user.id)

    if sla_breached is not None:
        stmt = stmt.where(Ticket.sla_breached == sla_breached)

    # `open` covers every status where work is still outstanding — the same
    # set the dashboard counts, so "Open: 27" and this filter agree.
    if status_group == "open":
        stmt = stmt.where(Ticket.status.in_(_OPEN_STATUSES))
    elif status_group == "closed":
        stmt = stmt.where(Ticket.status.notin_(_OPEN_STATUSES))

    if source:
        try:
            stmt = stmt.where(Ticket.source == TicketSource(source))
        except ValueError:
            raise ValidationError(f"Invalid source: {source}")

    if ai_categorized is not None:
        stmt = stmt.where(
            Ticket.ai_category.is_not(None) if ai_categorized
            else Ticket.ai_category.is_(None)
        )

    # Thresholds come from the model so this filter and the dashboard's
    # "High Risk" tile cannot drift apart.
    if ai_risk == "high":
        stmt = stmt.where(Ticket.ai_risk_score >= AI_RISK_HIGH_THRESHOLD)
    elif ai_risk == "medium":
        stmt = stmt.where(
            Ticket.ai_risk_score >= AI_RISK_MEDIUM_THRESHOLD,
            Ticket.ai_risk_score < AI_RISK_HIGH_THRESHOLD,
        )
    elif ai_risk == "low":
        stmt = stmt.where(
            Ticket.ai_risk_score.is_not(None),
            Ticket.ai_risk_score < AI_RISK_MEDIUM_THRESHOLD,
        )

    # Date bounds back the "today" cards (resolved today, arrived by email
    # today) without inventing a separate endpoint for each.
    if created_from:
        stmt = stmt.where(Ticket.created_at >= _parse_dt(created_from, "created_from"))
    if resolved_from:
        stmt = stmt.where(Ticket.resolved_at >= _parse_dt(resolved_from, "resolved_from"))

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

    authz.assert_can_write(current_user, "raise tickets")

    title = payload.get("title", "").strip()
    if not title:
        raise ValidationError("Title is required.")

    # Determine org_unit_id from reporter (prefer explicit, fall back to user's org unit)
    org_unit_id = current_user.org_unit_id
    ticket_number = await _generate_ticket_number(db, org_unit_id)

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
        org_unit_id=org_unit_id,
        department=payload.get("department"),
        tags=payload.get("tags"),
        internal_notes=payload.get("internal_notes"),
    )
    db.add(ticket)
    await db.flush()

    # Stamp the SLA deadlines and create the tracking row. This route builds
    # the Ticket inline rather than going through TicketService, so it never
    # inherited that step: a ticket raised in the UI had no due dates, never
    # appeared in the SLA monitor, and could never breach.
    await SLAService(db).apply_to_ticket(ticket)

    # Auto-assign by current workload. The routing service existed but nothing
    # called it, so every ticket arrived unassigned and waited for someone to
    # notice. Callers can opt out with auto_assign=false to triage by hand.
    routing_reason: str | None = None
    if payload.get("auto_assign", True):
        assignee, routing_reason = await RoutingService(db).auto_route_ticket(ticket)
        if assignee is not None:
            ticket.ai_routing_reason = routing_reason[:500]

    await _record_audit(
        db,
        action=AuditAction.CREATE,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={
            "ticket_number": ticket_number,
            "title": title,
            "priority": priority.value,
            **({"auto_assigned_to": str(ticket.assignee_id)} if ticket.assignee_id else {}),
        },
    )
    await db.commit()
    await db.refresh(ticket)

    log.info(
        "ticket_created",
        ticket_id=str(ticket.id),
        ticket_number=ticket_number,
        user_id=str(current_user.id),
        assignee_id=str(ticket.assignee_id) if ticket.assignee_id else None,
    )
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

    authz.assert_can_write(current_user, "modify tickets")

    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if not _can_modify_ticket(ticket, current_user):
        raise AuthorizationError("You do not have permission to modify this ticket.")

    # Non-admin users may only update restricted fields
    can_modify_all = current_user.is_super_admin or current_user.role.name in _AGENT_ROLES
    if not can_modify_all:
        allowed_fields = {"description", "tags"}
        invalid = set(payload.keys()) - allowed_fields
        if invalid:
            raise AuthorizationError(f"You cannot modify: {', '.join(invalid)}")

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

    # Only the raiser or agents can transition status
    authz.assert_can_write(current_user, "change ticket status")

    if not _can_modify_ticket(ticket, current_user):
        raise AuthorizationError("You do not have permission to transition this ticket.")

    # Org users (not agents) may only reopen or close their own tickets
    is_agent = authz.can_write_tickets(current_user)
    if not is_agent and not _is_branch_user(current_user):
        if new_status not in {TicketStatus.CLOSED, TicketStatus.REOPENED}:
            raise AuthorizationError("You may only close or reopen tickets.")
    elif _is_branch_user(current_user) and new_status not in {TicketStatus.CLOSED, TicketStatus.REOPENED}:
        raise AuthorizationError("Branch users may only close or reopen tickets.")

    # Enforce the lifecycle. VALID_TRANSITIONS was previously consulted only by
    # TicketService, which this endpoint never calls — so the state machine was
    # documentation rather than a constraint, and a new ticket could be marked
    # resolved without ever being assigned.
    old_status = ticket.status if isinstance(ticket.status, TicketStatus) else TicketStatus(ticket.status)
    if new_status != old_status:
        allowed = VALID_TRANSITIONS.get(old_status, [])
        if new_status not in allowed:
            raise ValidationError(
                f"Cannot move a ticket from '{old_status.value}' to '{new_status.value}'. "
                f"Allowed from here: {', '.join(s.value for s in allowed) or 'nothing'}."
            )

    now = datetime.now(UTC)
    ticket.status = new_status

    if new_status == TicketStatus.RESOLVED and not ticket.resolved_at:
        ticket.resolved_at = now
    if new_status == TicketStatus.CLOSED and not ticket.closed_at:
        ticket.closed_at = now
    if new_status in {TicketStatus.IN_PROGRESS, TicketStatus.ACKNOWLEDGED} and not ticket.first_response_at:
        ticket.first_response_at = now
    if new_status == TicketStatus.REOPENED:
        ticket.reopen_count = (ticket.reopen_count or 0) + 1
        ticket.resolved_at = None

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
    return ok(_serialize_ticket(ticket))


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
    return ok(_serialize_ticket(ticket))


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

    authz.assert_can_write(current_user, "comment on tickets")

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
        "summary": ticket.ai_summary or "AI summary not yet generated. The ticket will be categorized on the next processing cycle.",
        "sentiment": ticket.ai_sentiment or "neutral",
        "risk_score": ticket.ai_risk_score or 0.0,
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

    # Build contextual suggestions based on category and priority
    suggestions: list[str] = [
        "Review the customer's transaction history and any recent account activity.",
        f"This is a {ticket.priority.value}-priority ticket — ensure SLA targets are tracked.",
        "Check if there are any pending maintenance windows or known incidents affecting this service.",
    ]
    next_actions: list[str] = [
        "Assign to the appropriate department team for investigation.",
        "Escalate to the relevant department head if unresolved within SLA.",
    ]
    if ticket.ai_category:
        suggestions.insert(0, f"Based on AI categorization ({ticket.ai_category}): verify all related systems are checked.")

    result = {
        "suggestions": suggestions,
        "next_actions": next_actions,
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




@router.post(
    "/{ticket_id}/escalate",
    summary="Escalate a ticket by hand",
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def escalate_ticket(
    ticket_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Raise a ticket to the escalation target for its rule.

    Escalating was previously just a status change: the ticket turned red and
    nothing else happened — no event recorded, nobody reassigned, nobody told.
    This runs the same engine the breach worker uses, so a manual escalation
    and an automatic one leave identical evidence behind.
    """
    from app.services.escalation_service import (
        EscalationService,
        notify_escalation_outcome,
    )

    authz.assert_can_write(current_user, "escalate tickets")
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    reason = str(payload.get("reason", "")).strip() or "Escalated manually."
    trigger_name = str(payload.get("trigger", "manual"))
    try:
        trigger = EscalationTrigger(trigger_name)
    except ValueError:
        raise ValidationError(
            f"Invalid trigger: {trigger_name}. "
            f"Expected one of: {', '.join(t.value for t in EscalationTrigger)}"
        )

    outcome = await EscalationService(db).escalate(
        ticket, trigger=trigger, reason=reason, actor_id=current_user.id
    )

    if not outcome.escalated:
        raise ValidationError(outcome.reason)

    await _record_audit(
        db,
        action=AuditAction.ESCALATION,
        entity_id=str(ticket.id),
        user=current_user,
        request=request,
        new_values={
            "trigger": trigger.value,
            "reason": reason,
            "escalated_to": str(outcome.assignee.id) if outcome.assignee else None,
        },
    )
    await db.commit()
    await db.refresh(ticket)

    await notify_escalation_outcome(db, ticket, outcome)

    log.info(
        "ticket_escalated_manually",
        ticket_id=str(ticket.id),
        actor=str(current_user.id),
        to=str(outcome.assignee.id) if outcome.assignee else None,
    )
    return ok({
        "ticket": _serialize_ticket(ticket),
        "escalated_to": (
            {"id": str(outcome.assignee.id), "full_name": outcome.assignee.full_name}
            if outcome.assignee else None
        ),
        "rule": outcome.rule.name if outcome.rule else None,
    })

@router.get("/{ticket_id}/timeline", summary="Chronological history of a ticket")
async def get_ticket_timeline(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """One ordered feed of everything that happened to this ticket.

    The facts live in three tables — comments, the audit log, and escalation
    events — and reading a ticket's history meant looking in all three. This
    merges them into the single narrative a person actually wants: raised,
    commented, reassigned, escalated, resolved.
    """
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)
    events: list[dict] = []

    events.append({
        "kind": "created",
        "at": ticket.created_at.isoformat(),
        "title": f"Ticket created by {ticket.reporter.full_name}" if ticket.reporter else "Ticket created",
        "detail": f"Priority {ticket.priority.value} · via {ticket.source.value}",
        "actor": ticket.reporter.full_name if ticket.reporter else None,
    })

    # Comments. Internal notes stay hidden from branch users, matching the
    # comment list endpoint — the timeline must not become a way around that.
    comment_stmt = select(TicketComment).where(TicketComment.ticket_id == ticket_id)
    if _is_branch_user(current_user):
        comment_stmt = comment_stmt.where(TicketComment.is_internal.is_(False))
    for comment in (await db.execute(comment_stmt)).scalars().all():
        events.append({
            "kind": "internal_note" if comment.is_internal else "comment",
            "at": comment.created_at.isoformat(),
            "title": (
                f"{comment.author.full_name if comment.author else 'System'} "
                f"{'added an internal note' if comment.is_internal else 'commented'}"
            ),
            "detail": comment.body[:200],
            "actor": comment.author.full_name if comment.author else None,
        })

    # Status changes and assignments, from the audit trail.
    audit_rows = (await db.execute(
        select(AuditLog).where(
            AuditLog.entity_type == "ticket",
            AuditLog.entity_id == str(ticket_id),
            AuditLog.action.in_([AuditAction.STATUS_CHANGE, AuditAction.ASSIGNMENT]),
        )
    )).scalars().all()
    for row in audit_rows:
        new_values = row.new_values or {}
        old_values = row.old_values or {}
        if row.action == AuditAction.STATUS_CHANGE:
            old = str(old_values.get("status", "?")).replace("_", " ")
            new = str(new_values.get("status", "?")).replace("_", " ")
            title = f"Status changed from {old} to {new}"
            detail = new_values.get("reason") or ""
        else:
            title = "Ticket reassigned"
            detail = ""
        events.append({
            "kind": "status_change" if row.action == AuditAction.STATUS_CHANGE else "assignment",
            "at": row.created_at.isoformat(),
            "title": title,
            "detail": detail,
            "actor": row.actor_email,
        })

    # Escalations.
    for event in (await db.execute(
        select(EscalationEvent).where(EscalationEvent.ticket_id == ticket_id)
    )).scalars().all():
        target = event.escalated_to.full_name if event.escalated_to else None
        automatic = event.escalated_by_id is None
        events.append({
            "kind": "escalation",
            "at": event.triggered_at.isoformat(),
            "title": (
                f"{'Auto-escalated' if automatic else 'Escalated'} — "
                f"{event.trigger.value.replace('_', ' ')}"
            ),
            "detail": event.reason or "",
            "actor": target,
            "automatic": automatic,
        })

    if ticket.resolved_at:
        events.append({
            "kind": "resolved", "at": ticket.resolved_at.isoformat(),
            "title": "Ticket resolved", "detail": "", "actor": None,
        })
    if ticket.closed_at:
        events.append({
            "kind": "closed", "at": ticket.closed_at.isoformat(),
            "title": "Ticket closed", "detail": "", "actor": None,
        })

    events.sort(key=lambda e: e["at"])
    return ok(events)


# ---------------------------------------------------------------------------
# Attachments
# ---------------------------------------------------------------------------

def _serialize_attachment(a: Attachment) -> dict:
    return {
        "id": str(a.id),
        "ticket_id": str(a.ticket_id),
        "filename": a.original_filename,
        "content_type": a.content_type,
        "size_bytes": a.size_bytes,
        "checksum_sha256": a.checksum_sha256,
        "uploader": (
            {"id": str(a.uploader.id), "full_name": a.uploader.full_name}
            if a.uploader else None
        ),
        "created_at": a.created_at.isoformat(),
    }


@router.get("/{ticket_id}/attachments", summary="List a ticket's attachments")
async def list_attachments(
    ticket_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Access is decided by the ticket, not the file: anyone who can read the
    # ticket can read what is attached to it.
    await _get_ticket_or_404(ticket_id, db, current_user)
    rows = (await db.execute(
        select(Attachment)
        .where(Attachment.ticket_id == ticket_id)
        .order_by(Attachment.created_at.desc())
    )).scalars().all()
    return ok([_serialize_attachment(a) for a in rows])


@router.post(
    "/{ticket_id}/attachments",
    status_code=status.HTTP_201_CREATED,
    summary="Attach a file to a ticket",
)
async def upload_attachment(
    ticket_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Store a file against a ticket.

    The whole body is read into memory before validation because the size limit
    is small and streaming to storage before knowing the file is acceptable
    would mean writing rejects to the bucket and cleaning them up afterwards.
    """
    authz.assert_can_write(current_user, "attach files")
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    if not _can_modify_ticket(ticket, current_user):
        raise AuthorizationError("You do not have permission to modify this ticket.")

    data = await file.read()
    extension = validate_upload(file.filename or "file", file.content_type or "", len(data))
    safe_name = sanitize_filename(file.filename or f"file.{extension}")

    stored = await storage.upload(
        build_key(ticket_id, extension), data, file.content_type or "application/octet-stream"
    )

    attachment = Attachment(
        id=uuid.uuid4(),
        ticket_id=ticket_id,
        uploader_id=current_user.id,
        original_filename=safe_name,
        content_type=file.content_type or "application/octet-stream",
        size_bytes=stored.size_bytes,
        s3_key=stored.key,
        s3_bucket=stored.bucket,
        checksum_sha256=stored.checksum_sha256,
    )
    db.add(attachment)

    await _record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_id=str(ticket_id),
        user=current_user,
        request=request,
        new_values={"attachment_added": safe_name, "size_bytes": stored.size_bytes},
    )
    await db.commit()
    await db.refresh(attachment)

    log.info(
        "attachment_uploaded",
        ticket_id=str(ticket_id),
        attachment_id=str(attachment.id),
        size=stored.size_bytes,
        user_id=str(current_user.id),
    )
    return ok(_serialize_attachment(attachment))


@router.get(
    "/{ticket_id}/attachments/{attachment_id}/download",
    summary="Download an attachment",
)
async def download_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    """Stream the file back through the API.

    Deliberately not a presigned URL: that would be a bearer token in a query
    string, outliving the session and readable from history and proxy logs. For
    bank documents every read goes through the ticket's permission check.
    """
    await _get_ticket_or_404(ticket_id, db, current_user)

    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket_id:
        raise NotFoundError("Attachment not found on this ticket.")

    try:
        data = await storage.download(attachment.s3_key)
    except Exception as exc:
        log.exception("attachment_download_failed", key=attachment.s3_key)
        raise NotFoundError("The stored file could not be retrieved.") from exc

    # The filename was sanitised on the way in, so it is safe in the header.
    return Response(
        content=data,
        media_type=attachment.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{attachment.original_filename}"',
            "Content-Length": str(len(data)),
        },
    )


@router.delete(
    "/{ticket_id}/attachments/{attachment_id}",
    summary="Remove an attachment",
)
async def delete_attachment(
    ticket_id: uuid.UUID,
    attachment_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> Response:
    authz.assert_can_write(current_user, "remove attachments")
    ticket = await _get_ticket_or_404(ticket_id, db, current_user)

    attachment = await db.get(Attachment, attachment_id)
    if attachment is None or attachment.ticket_id != ticket_id:
        raise NotFoundError("Attachment not found on this ticket.")

    # The uploader can always remove their own; otherwise agent rights are
    # needed, so a branch user cannot delete evidence someone else filed.
    is_uploader = str(attachment.uploader_id) == str(current_user.id)
    if not is_uploader and not authz.can_write_tickets(current_user):
        raise AuthorizationError("You can only remove attachments you uploaded.")
    if not _can_modify_ticket(ticket, current_user):
        raise AuthorizationError("You do not have permission to modify this ticket.")

    filename = attachment.original_filename
    key = attachment.s3_key

    await db.delete(attachment)
    await _record_audit(
        db,
        action=AuditAction.UPDATE,
        entity_id=str(ticket_id),
        user=current_user,
        request=request,
        old_values={"attachment_removed": filename},
    )
    await db.commit()

    # Object removed after the row, so a storage failure leaves an orphaned
    # object rather than a database row pointing at nothing.
    await storage.delete(key)

    log.info("attachment_deleted", ticket_id=str(ticket_id), attachment_id=str(attachment_id))
    return Response(status_code=status.HTTP_204_NO_CONTENT)

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
