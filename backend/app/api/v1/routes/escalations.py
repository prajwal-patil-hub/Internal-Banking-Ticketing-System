"""Escalation rules & event log.

* GET /escalations/rules        — list rules    (admin, supervisor)
* GET /escalations/events       — list event log (admin, supervisor, auditor)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_roles
from app.models.escalation import EscalationEvent, EscalationRule
from app.schemas.envelope import paginated

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get(
    "/rules",
    summary="List escalation rules",
    dependencies=[Depends(require_roles("admin", "supervisor"))],
)
async def list_rules(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    is_active: Annotated[bool | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(EscalationRule)
    if is_active is not None:
        stmt = stmt.where(EscalationRule.is_active == is_active)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(EscalationRule.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": str(r.id),
            "name": r.name,
            "trigger": r.trigger.value,
            "trigger_after_minutes": r.trigger_after_minutes,
            "escalate_to_role": r.escalate_to_role,
            "escalate_to_user_id": str(r.escalate_to_user_id) if r.escalate_to_user_id else None,
            "notify_email": r.notify_email,
            "category_id": str(r.category_id) if r.category_id else None,
            "priority_threshold": r.priority_threshold,
            "is_active": r.is_active,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]
    return paginated(items, page=page, size=per_page, total=total)


@router.get(
    "/events",
    summary="List escalation events (audit log)",
    dependencies=[Depends(require_roles("admin", "supervisor", "auditor"))],
)
async def list_events(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    trigger: Annotated[str | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(EscalationEvent)
    if trigger:
        stmt = stmt.where(EscalationEvent.trigger == trigger)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(EscalationEvent.triggered_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": str(e.id),
            "ticket_id": str(e.ticket_id),
            "rule_id": str(e.rule_id) if e.rule_id else None,
            "rule_name": e.rule.name if e.rule else None,
            "trigger": e.trigger.value,
            "triggered_at": e.triggered_at.isoformat(),
            "escalated_to_id": str(e.escalated_to_id) if e.escalated_to_id else None,
            "escalated_to_email": e.escalated_to.email if e.escalated_to else None,
            "escalated_by_id": str(e.escalated_by_id) if e.escalated_by_id else None,
            "escalated_by_email": e.escalated_by.email if e.escalated_by else None,
            "reason": e.reason,
            "resolved_at": e.resolved_at.isoformat() if e.resolved_at else None,
        }
        for e in rows
    ]
    return paginated(items, page=page, size=per_page, total=total)
