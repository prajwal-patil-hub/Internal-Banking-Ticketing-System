"""Branch management endpoints.

* GET /branches              — list (any authenticated user)
* POST /branches             — create (admin only)
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import ConflictError, ValidationError
from app.models.branch import Branch
from app.schemas.envelope import ok, paginated

router = APIRouter(prefix="/branches", tags=["branches"])


def _serialize(b: Branch) -> dict:
    return {
        "id": str(b.id),
        "code": b.code,
        "name": b.name,
        "region": b.region,
        "address": b.address,
        "ifsc": b.ifsc,
        "contact_email": b.contact_email,
        "contact_phone": b.contact_phone,
        "is_active": b.is_active,
        "created_at": b.created_at.isoformat(),
    }


@router.get("", summary="List branches", dependencies=[Depends(get_current_user)])
async def list_branches(
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
    search: Annotated[str | None, Query(max_length=200)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(Branch)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(
            or_(
                Branch.code.ilike(term),
                Branch.name.ilike(term),
                Branch.region.ilike(term),
                Branch.ifsc.ilike(term),
            )
        )
    if is_active is not None:
        stmt = stmt.where(Branch.is_active == is_active)

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(Branch.name.asc()).offset((page - 1) * per_page).limit(per_page)
    rows = (await db.execute(stmt)).scalars().all()
    return paginated([_serialize(b) for b in rows], page=page, size=per_page, total=total)


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a branch",
    dependencies=[Depends(require_roles("admin"))],
)
async def create_branch(payload: dict, db: AsyncSession = Depends(get_session)) -> dict:
    code = (payload.get("code") or "").strip().upper()
    name = (payload.get("name") or "").strip()
    if not code or not name:
        raise ValidationError("code and name are required.")

    existing = (await db.execute(select(Branch).where(Branch.code == code))).scalar_one_or_none()
    if existing is not None:
        raise ConflictError(f"Branch with code {code} already exists.")

    branch = Branch(
        code=code,
        name=name,
        region=(payload.get("region") or "").strip(),
        address=(payload.get("address") or "").strip(),
        ifsc=(payload.get("ifsc") or "").strip().upper(),
        contact_email=(payload.get("contact_email") or "").strip(),
        contact_phone=(payload.get("contact_phone") or "").strip(),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(branch)
    await db.commit()
    await db.refresh(branch)
    return ok(_serialize(branch))
