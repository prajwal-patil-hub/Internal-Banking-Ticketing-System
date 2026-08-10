"""Escalation rules and events API."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.models.escalation import EscalationEvent, EscalationRule
from app.models.ticket import Ticket
from app.models.user import User
from app.schemas.envelope import ok, paginated

router = APIRouter(prefix="/escalations", tags=["escalations"])


def _serialize_rule(rule: EscalationRule) -> dict:
    return {
        "id": str(rule.id),
        "name": rule.name,
        "trigger": rule.trigger.value,
        "trigger_after_minutes": rule.trigger_after_minutes,
        "escalate_to_role": rule.escalate_to_role,
        "escalate_to_user_id": str(rule.escalate_to_user_id) if rule.escalate_to_user_id else None,
        "escalate_to_user": {
            "id": str(rule.escalate_to_user.id),
            "email": rule.escalate_to_user.email,
            "full_name": rule.escalate_to_user.full_name,
        } if rule.escalate_to_user else None,
        "notify_email": rule.notify_email,
        "is_active": rule.is_active,
        "priority_threshold": rule.priority_threshold,
        "category_id": str(rule.category_id) if rule.category_id else None,
        "category": {
            "id": str(rule.category.id),
            "name": rule.category.name,
            "code": rule.category.code,
        } if rule.category else None,
        "created_at": rule.created_at.isoformat(),
    }


def _serialize_event(event: EscalationEvent) -> dict:
    return {
        "id": str(event.id),
        "ticket_id": str(event.ticket_id),
        "rule_id": str(event.rule_id) if event.rule_id else None,
        "rule_name": event.rule.name if event.rule else None,
        "trigger": event.trigger.value,
        "triggered_at": event.triggered_at.isoformat(),
        "escalated_to": {
            "id": str(event.escalated_to.id),
            "email": event.escalated_to.email,
            "full_name": event.escalated_to.full_name,
        } if event.escalated_to else None,
        "escalated_by": {
            "id": str(event.escalated_by.id),
            "email": event.escalated_by.email,
            "full_name": event.escalated_by.full_name,
        } if event.escalated_by else None,
        "reason": event.reason,
        "resolved_at": event.resolved_at.isoformat() if event.resolved_at else None,
    }


@router.get(
    "/rules",
    summary="List escalation rules",
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def list_rules(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(EscalationRule).order_by(EscalationRule.created_at.desc())
    )
    rules = result.scalars().all()
    return ok([_serialize_rule(r) for r in rules])


@router.get(
    "/events",
    summary="List escalation events",
    dependencies=[Depends(require_roles("supervisor", "admin"))],
)
async def list_events(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    ticket_id: Annotated[uuid.UUID | None, Query()] = None,
    unresolved_only: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func

    stmt = select(EscalationEvent)
    if ticket_id:
        stmt = stmt.where(EscalationEvent.ticket_id == ticket_id)
    if unresolved_only:
        stmt = stmt.where(EscalationEvent.resolved_at.is_(None))

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(EscalationEvent.triggered_at.desc()).offset((page - 1) * per_page).limit(per_page)
    events = (await db.execute(stmt)).scalars().all()

    return paginated(
        [_serialize_event(e) for e in events],
        page=page,
        size=per_page,
        total=total,
    )
