"""Ticket endpoints — list/get/create.

Workflow transitions, comments and attachments arrive in P3.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.models.user import User
from app.repositories.ticket_repo import TicketFilter
from app.schemas.envelope import ok, paginated
from app.schemas.ticket import TicketCreate, TicketPublic, TicketSummary
from app.services.ticket_service import TicketService
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/tickets", tags=["tickets"])


@router.get("")
async def list_tickets(
    p: PageParams = Depends(page_params),
    status: list[str] | None = Query(default=None),
    priority: list[str] | None = Query(default=None),
    branch_id: uuid.UUID | None = Query(default=None),
    assigned_user_id: uuid.UUID | None = Query(default=None),
    breached: bool | None = Query(default=None),
    q: str | None = Query(default=None),
    date_from: datetime | None = Query(default=None),
    date_to: datetime | None = Query(default=None),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    f = TicketFilter(
        status=status, priority=priority, branch_id=branch_id,
        assigned_user_id=assigned_user_id, breached=breached, q=q,
        date_from=date_from, date_to=date_to,
    )
    items, total = await TicketService(db).list_for(user, f=f, offset=p.offset, limit=p.limit)
    return paginated(
        [TicketSummary.model_validate(t).model_dump(mode="json") for t in items],
        page=p.page, size=p.size, total=total,
    )


@router.get("/{ticket_id}")
async def get_ticket(
    ticket_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    t = await TicketService(db).get_for(user, ticket_id)
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))


@router.post("")
async def create_ticket(
    payload: TicketCreate,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(require_permissions("ticket.create")),
) -> dict:
    t = await TicketService(db).create(
        actor=user,
        branch_id=payload.branch_id,
        category_id=payload.category_id,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
    )
    await db.commit()
    return ok(TicketPublic.model_validate(t).model_dump(mode="json"))
