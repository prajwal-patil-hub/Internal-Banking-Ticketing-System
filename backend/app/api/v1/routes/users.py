"""User & role endpoints.

* GET /users/me              — current user (any role)
* GET /users                 — list users  (admin, supervisor)
* GET /roles                 — list roles + permissions (admin)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.models.role import Role
from app.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.envelope import ok, paginated

router = APIRouter(prefix="/users", tags=["users"])
roles_router = APIRouter(prefix="/roles", tags=["roles"])


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


@router.get(
    "",
    summary="List users (paginated, filtered)",
    dependencies=[Depends(require_roles("admin", "supervisor"))],
)
async def list_users(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    search: Annotated[str | None, Query(max_length=200)] = None,
    role: Annotated[str | None, Query()] = None,
    is_active: Annotated[bool | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(User).join(Role, User.role_id == Role.id)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(or_(User.email.ilike(term), User.full_name.ilike(term)))
    if role:
        stmt = stmt.where(Role.name == role)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()

    stmt = stmt.order_by(User.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()

    items = [
        {
            "id": str(u.id),
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name,
            "branch_id": str(u.branch_id) if u.branch_id else None,
            "is_active": u.is_active,
            "mfa_enabled": u.mfa_enabled,
            "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None,
            "created_at": u.created_at.isoformat(),
        }
        for u in rows
    ]
    return paginated(items, page=page, size=per_page, total=total)


@roles_router.get(
    "",
    summary="List roles with their permissions",
    dependencies=[Depends(require_roles("admin", "supervisor", "auditor"))],
)
async def list_roles(db: AsyncSession = Depends(get_session)) -> dict:
    rows = (await db.execute(select(Role).order_by(Role.name.asc()))).scalars().all()
    items = [
        {
            "id": str(r.id),
            "name": r.name,
            "description": r.description,
            "permissions": sorted(p.code for p in r.permissions),
        }
        for r in rows
    ]
    return ok(items)
