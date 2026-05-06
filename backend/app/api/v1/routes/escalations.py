"""Escalation endpoints — list + manual resolve."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_permissions
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories.escalation_repo import EscalationRepository
from app.schemas.envelope import ok, paginated
from app.schemas.notification import EscalationPublic
from app.services.escalation_service import EscalationService
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/escalations", tags=["escalations"])


@router.get("")
async def list_escalations(
    p: PageParams = Depends(page_params),
    open_only: bool = Query(default=False),
    ticket_id: uuid.UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("escalation.handle")),
) -> dict:
    items, total = await EscalationRepository(db).list(
        ticket_id=ticket_id, open_only=open_only, offset=p.offset, limit=p.limit,
    )
    return paginated(
        [EscalationPublic.model_validate(e).model_dump(mode="json") for e in items],
        page=p.page, size=p.size, total=total,
    )


@router.post("/{escalation_id}/resolve")
async def resolve_escalation(
    escalation_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("escalation.handle")),
) -> dict:
    e = await EscalationService(db).resolve(escalation_id=escalation_id)
    if e is None:
        raise NotFoundError("Escalation not found.")
    await db.commit()
    return ok(EscalationPublic.model_validate(e).model_dump(mode="json"))
