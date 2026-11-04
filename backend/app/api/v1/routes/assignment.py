"""Assignment control: who is available, who owns a category, and the safety-net delay.

These endpoints exist because auto-assignment stopped being an invisible rule
applied at creation and became something people operate. A supervisor needs to
see the queue before choosing an owner, name the desk that handles a category,
and know how long an untouched ticket waits before the system steps in.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.assignment import AssignmentRule
from app.models.audit import AuditAction, AuditLog
from app.models.role import Role
from app.models.ticket import TicketCategory
from app.models.user import User
from app.schemas.envelope import ok
from app.services.routing_service import ASSIGNABLE_ROLES, RoutingService, is_on_leave
from app.services.settings_service import MAX_DELAY_HOURS, MIN_DELAY_HOURS, SettingsService

log = get_logger(__name__)

router = APIRouter(prefix="/assignment", tags=["assignment"])


def _rule_json(rule: AssignmentRule) -> dict:
    return {
        "id": str(rule.id),
        "category_id": str(rule.category_id),
        "category_name": rule.category.name if rule.category else None,
        "assignee_id": str(rule.assignee_id),
        "assignee_name": rule.assignee.full_name if rule.assignee else None,
        "assignee_on_leave": is_on_leave(rule.assignee) if rule.assignee else False,
        "note": rule.note,
    }


# ---------------------------------------------------------------- workload ---
@router.get(
    "/workload",
    summary="Who can take a ticket, with their current open count and leave state",
    # Agents can see this because they can assign; it is the list behind the
    # assign control, not a management report.
    dependencies=[Depends(require_roles("agent", "supervisor", "admin"))],
)
async def get_workload(db: AsyncSession = Depends(get_session)) -> dict:
    return ok(await RoutingService(db).get_agent_workload())


# ------------------------------------------------------------------- rules ---
@router.get(
    "/rules",
    summary="Category routing rules",
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def list_rules(db: AsyncSession = Depends(get_session)) -> dict:
    rows = (await db.execute(select(AssignmentRule))).scalars().all()
    return ok([_rule_json(r) for r in rows])


@router.put(
    "/rules",
    summary="Point a category at a person (creates or replaces that category's rule)",
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def upsert_rule(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    try:
        category_id = uuid.UUID(str(payload.get("category_id")))
        assignee_id = uuid.UUID(str(payload.get("assignee_id")))
    except (TypeError, ValueError):
        raise ValidationError("category_id and assignee_id are required and must be UUIDs.")

    if await db.get(TicketCategory, category_id) is None:
        raise NotFoundError(f"Category {category_id} not found.")

    # The named person must be able to hold a ticket. A rule pointing at an
    # auditor or a branch user would route work somewhere it can never be
    # actioned, and the failure would only surface as tickets going quiet.
    assignee = (await db.execute(
        select(User).join(Role, Role.id == User.role_id).where(
            User.id == assignee_id,
            User.is_active.is_(True),
            Role.name.in_(ASSIGNABLE_ROLES),
        )
    )).scalar_one_or_none()
    if assignee is None:
        raise ValidationError(
            "The assignee must be an active agent or supervisor. "
            "Only those roles can be given a ticket."
        )

    note = (payload.get("note") or "").strip()[:200] or None

    rule = (await db.execute(
        select(AssignmentRule).where(AssignmentRule.category_id == category_id)
    )).scalar_one_or_none()
    if rule is None:
        rule = AssignmentRule(
            category_id=category_id,
            assignee_id=assignee_id,
            note=note,
            created_by_id=current_user.id,
        )
        db.add(rule)
    else:
        rule.assignee_id = assignee_id
        rule.note = note

    db.add(AuditLog(
        action=AuditAction.UPDATE,
        entity_type="assignment_rule",
        entity_id=str(category_id),
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.name if current_user.role else None,
        ip_address=request.client.host if request.client else None,
        new_values={"category_id": str(category_id), "assignee_id": str(assignee_id)},
    ))
    await db.commit()
    await db.refresh(rule)
    log.info("assignment_rule_set", category_id=str(category_id), assignee_id=str(assignee_id))
    return ok(_rule_json(rule))


@router.delete(
    "/rules/{category_id}",
    summary="Remove a category's routing rule",
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def delete_rule(
    category_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    rule = (await db.execute(
        select(AssignmentRule).where(AssignmentRule.category_id == category_id)
    )).scalar_one_or_none()
    if rule is None:
        raise NotFoundError("No routing rule for that category.")
    await db.delete(rule)
    db.add(AuditLog(
        action=AuditAction.DELETE,
        entity_type="assignment_rule",
        entity_id=str(category_id),
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.name if current_user.role else None,
        ip_address=request.client.host if request.client else None,
        old_values={"assignee_id": str(rule.assignee_id)},
    ))
    await db.commit()
    log.info("assignment_rule_deleted", category_id=str(category_id))
    return ok({"deleted": True})


# ---------------------------------------------------------------- settings ---
@router.get(
    "/settings",
    summary="Auto-assignment settings",
    # Readable by supervisors: they need to know how long they have to triage
    # before the system assigns for them.
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def get_settings(db: AsyncSession = Depends(get_session)) -> dict:
    hours = await SettingsService(db).get_auto_assign_delay_hours()
    return ok({
        "auto_assign_delay_hours": hours,
        "min_hours": MIN_DELAY_HOURS,
        "max_hours": MAX_DELAY_HOURS,
    })


@router.put(
    "/settings",
    summary="Change how long a ticket may sit unassigned",
    dependencies=[Depends(require_roles("admin"))],
)
async def put_settings(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    raw = payload.get("auto_assign_delay_hours")
    try:
        hours = float(raw)
    except (TypeError, ValueError):
        raise ValidationError("auto_assign_delay_hours must be a number of hours.")
    if hours < MIN_DELAY_HOURS or hours > MAX_DELAY_HOURS:
        raise ValidationError(
            f"auto_assign_delay_hours must be between {MIN_DELAY_HOURS} and {MAX_DELAY_HOURS}."
        )

    value = await SettingsService(db).set_auto_assign_delay_hours(hours, current_user.id)
    db.add(AuditLog(
        action=AuditAction.UPDATE,
        entity_type="system_setting",
        entity_id="auto_assign_delay_hours",
        actor_id=current_user.id,
        actor_email=current_user.email,
        actor_role=current_user.role.name if current_user.role else None,
        ip_address=request.client.host if request.client else None,
        new_values={"auto_assign_delay_hours": value},
    ))
    await db.commit()
    return ok({"auto_assign_delay_hours": value})
