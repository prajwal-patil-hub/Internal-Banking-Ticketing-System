"""Audit-log endpoints — read-only, auditor permission required."""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_permissions
from app.models.user import User
from app.repositories.audit_repo import AuditRepository
from app.schemas.audit import AuditLogPublic
from app.schemas.envelope import paginated
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/audit-logs", tags=["audit"])


@router.get("")
async def list_audit_logs(
    p: PageParams = Depends(page_params),
    entity_type: str | None = Query(default=None),
    entity_id: uuid.UUID | None = Query(default=None),
    action: str | None = Query(default=None),
    actor_user_id: uuid.UUID | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("audit.read")),
) -> dict:
    items, total = await AuditRepository(db).list(
        entity_type=entity_type,
        entity_id=entity_id,
        action=action,
        actor_user_id=actor_user_id,
        date_from=date_from,
        date_to=date_to,
        offset=p.offset,
        limit=p.limit,
    )
    return paginated(
        [AuditLogPublic.model_validate(a).model_dump(mode="json") for a in items],
        page=p.page, size=p.size, total=total,
    )
