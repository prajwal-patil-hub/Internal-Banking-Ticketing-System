"""Self-notification endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.exceptions import NotFoundError
from app.models.user import User
from app.repositories.notification_repo import NotificationRepository
from app.schemas.envelope import ok, paginated
from app.schemas.notification import NotificationPublic
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("")
async def list_my_notifications(
    p: PageParams = Depends(page_params),
    channel: str | None = Query(default="in_app"),
    unread: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    items, total = await NotificationRepository(db).list_for_user(
        user.id, channel=channel, unread_only=unread, offset=p.offset, limit=p.limit,
    )
    return paginated(
        [NotificationPublic.model_validate(n).model_dump(mode="json") for n in items],
        page=p.page, size=p.size, total=total,
    )


@router.get("/unread-count")
async def my_unread_count(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    count = await NotificationRepository(db).unread_count(user.id)
    return ok({"unread": count})


@router.post("/{notification_id}/read")
async def mark_read(
    notification_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    repo = NotificationRepository(db)
    n = await repo.get(notification_id)
    if n is None or n.user_id != user.id:
        raise NotFoundError("Notification not found.")
    await repo.mark_read(n)
    await db.commit()
    return ok(NotificationPublic.model_validate(n).model_dump(mode="json"))


@router.post("/mark-all-read")
async def mark_all_read(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    count = await NotificationRepository(db).mark_all_read(user.id)
    await db.commit()
    return ok({"marked": count})
