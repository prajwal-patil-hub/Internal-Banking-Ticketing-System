"""Audit log API routes.

Read-only endpoints for compliance and auditing. Restricted to
admin and auditor roles only.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.logging import get_logger
from app.models.audit import AuditAction, AuditLog
from app.models.user import User
from app.schemas.envelope import paginated

log = get_logger(__name__)

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[Depends(require_roles("admin", "auditor"))],
)


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def _serialize_audit_log(entry: AuditLog) -> dict:
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
        "user_agent": entry.user_agent,
        "request_id": entry.request_id,
        "metadata": entry.metadata_,
        "created_at": entry.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", summary="Get audit logs with filters")
async def list_audit_logs(
    request: Request,
    entity_type: Annotated[str | None, Query(max_length=50)] = None,
    entity_id: Annotated[str | None, Query(max_length=36)] = None,
    actor_id: Annotated[uuid.UUID | None, Query()] = None,
    action: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    conditions = []

    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)
    if entity_id:
        conditions.append(AuditLog.entity_id == entity_id)
    if actor_id:
        conditions.append(AuditLog.actor_id == actor_id)
    if action:
        try:
            action_enum = AuditAction(action)
            conditions.append(AuditLog.action == action_enum)
        except ValueError:
            from app.core.exceptions import ValidationError
            raise ValidationError(
                f"Invalid action value: {action}. Valid values: {[a.value for a in AuditAction]}"
            )

    where_clause = and_(*conditions) if conditions else None

    count_stmt = select(func.count(AuditLog.id))
    if where_clause is not None:
        count_stmt = count_stmt.where(where_clause)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = select(AuditLog)
    if where_clause is not None:
        stmt = stmt.where(where_clause)
    stmt = stmt.order_by(AuditLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page)

    result = await db.execute(stmt)
    entries = result.scalars().all()

    return paginated(
        [_serialize_audit_log(e) for e in entries],
        page=page,
        size=per_page,
        total=total,
    )


@router.get("/entities/{entity_type}/{entity_id}", summary="Audit trail for a specific entity")
async def get_entity_audit_trail(
    entity_type: str,
    entity_id: str,
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    count_stmt = select(func.count(AuditLog.id)).where(
        and_(
            AuditLog.entity_type == entity_type,
            AuditLog.entity_id == entity_id,
        )
    )
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(AuditLog)
        .where(
            and_(
                AuditLog.entity_type == entity_type,
                AuditLog.entity_id == entity_id,
            )
        )
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    return paginated(
        [_serialize_audit_log(e) for e in entries],
        page=page,
        size=per_page,
        total=total,
    )


@router.get("/actors/{user_id}", summary="All audit actions by a specific user")
async def get_actor_audit_trail(
    user_id: uuid.UUID,
    request: Request,
    action: Annotated[str | None, Query()] = None,
    entity_type: Annotated[str | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 50,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    conditions = [AuditLog.actor_id == user_id]

    if action:
        try:
            action_enum = AuditAction(action)
            conditions.append(AuditLog.action == action_enum)
        except ValueError:
            from app.core.exceptions import ValidationError
            raise ValidationError(f"Invalid action value: {action}")
    if entity_type:
        conditions.append(AuditLog.entity_type == entity_type)

    where_clause = and_(*conditions)

    count_stmt = select(func.count(AuditLog.id)).where(where_clause)
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(AuditLog)
        .where(where_clause)
        .order_by(AuditLog.created_at.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
    )
    result = await db.execute(stmt)
    entries = result.scalars().all()

    log.info(
        "audit_actor_trail_accessed",
        actor_id=str(user_id),
        accessed_by=str(current_user.id),
    )

    return paginated(
        [_serialize_audit_log(e) for e in entries],
        page=page,
        size=per_page,
        total=total,
    )
