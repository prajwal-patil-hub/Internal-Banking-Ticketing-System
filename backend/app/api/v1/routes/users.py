"""User self + admin user list."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.envelope import ok, paginated
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return ok(
        UserPublic.model_validate(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.name,
                "branch_id": user.branch_id,
                "mfa_enabled": user.mfa_enabled,
            }
        ).model_dump(mode="json")
    )


@router.get("")
async def list_users(
    p: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_session),
    _admin: User = Depends(require_permissions("user.manage")),
) -> dict:
    total = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    rows = (
        await db.execute(
            select(User).order_by(User.created_at.desc()).offset(p.offset).limit(p.limit)
        )
    ).scalars().all()
    items = [
        UserPublic.model_validate(
            {
                "id": u.id, "email": u.email, "full_name": u.full_name,
                "role": u.role.name, "branch_id": u.branch_id,
                "mfa_enabled": u.mfa_enabled,
            }
        ).model_dump(mode="json")
        for u in rows
    ]
    return paginated(items, page=p.page, size=p.size, total=total)
