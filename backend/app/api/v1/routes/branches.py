"""Branch admin endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.core.exceptions import ConflictError, NotFoundError
from app.models.branch import Branch
from app.models.user import User
from app.repositories.branch_repo import BranchRepository
from app.schemas.branch import BranchCreate, BranchPublic, BranchUpdate
from app.schemas.envelope import ok, paginated
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/branches", tags=["branches"])


@router.get("")
async def list_branches(
    p: PageParams = Depends(page_params),
    q: str | None = Query(default=None),
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    items, total = await BranchRepository(db).list(
        q=q, offset=p.offset, limit=p.limit, include_inactive=include_inactive,
    )
    return paginated(
        [BranchPublic.model_validate(b).model_dump(mode="json") for b in items],
        page=p.page, size=p.size, total=total,
    )


@router.get("/{branch_id}")
async def get_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    b = await BranchRepository(db).get(branch_id)
    if b is None:
        raise NotFoundError("Branch not found.")
    return ok(BranchPublic.model_validate(b).model_dump(mode="json"))


@router.post("")
async def create_branch(
    payload: BranchCreate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("branch.manage")),
) -> dict:
    repo = BranchRepository(db)
    if await repo.get_by_code(payload.code):
        raise ConflictError("Branch code already exists.")
    b = Branch(
        code=payload.code.upper().strip(),
        name=payload.name.strip(),
        region=payload.region,
        address=payload.address,
        ifsc=payload.ifsc.upper().strip(),
        contact_email=payload.contact_email,
        contact_phone=payload.contact_phone,
    )
    await repo.create(b)
    await db.commit()
    return ok(BranchPublic.model_validate(b).model_dump(mode="json"))


@router.patch("/{branch_id}")
async def update_branch(
    branch_id: uuid.UUID,
    payload: BranchUpdate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("branch.manage")),
) -> dict:
    b = await BranchRepository(db).get(branch_id)
    if b is None:
        raise NotFoundError("Branch not found.")
    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        if value is None:
            continue
        if field == "ifsc":
            value = (value or "").upper().strip()
        if field == "name":
            value = (value or "").strip()
        setattr(b, field, value)
    await db.commit()
    return ok(BranchPublic.model_validate(b).model_dump(mode="json"))


@router.delete("/{branch_id}")
async def soft_delete_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("branch.manage")),
) -> dict:
    """Soft delete: flips is_active=false. Hard delete is intentionally
    unavailable to preserve referential integrity with tickets."""
    b = await BranchRepository(db).get(branch_id)
    if b is None:
        raise NotFoundError("Branch not found.")
    b.is_active = False
    await db.commit()
    return ok(BranchPublic.model_validate(b).model_dump(mode="json"))


@router.post("/{branch_id}/restore")
async def restore_branch(
    branch_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("branch.manage")),
) -> dict:
    b = await BranchRepository(db).get(branch_id)
    if b is None:
        raise NotFoundError("Branch not found.")
    b.is_active = True
    await db.commit()
    return ok(BranchPublic.model_validate(b).model_dump(mode="json"))
