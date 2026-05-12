from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.core.exceptions import NotFoundError
from app.models.category import Category
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryPublic, CategoryUpdate
from app.schemas.envelope import ok, paginated
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(
    p: PageParams = Depends(page_params),
    include_inactive: bool = Query(default=False),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    items, total = await CategoryRepository(db).list(
        offset=p.offset, limit=p.limit, include_inactive=include_inactive,
    )
    return paginated(
        [CategoryPublic.model_validate(c).model_dump(mode="json") for c in items],
        page=p.page, size=p.size, total=total,
    )


@router.post("")
async def create_category(
    payload: CategoryCreate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("category.manage")),
) -> dict:
    c = Category(
        name=payload.name.strip(),
        description=payload.description,
        default_priority=payload.default_priority,
    )
    await CategoryRepository(db).create(c)
    await db.commit()
    return ok(CategoryPublic.model_validate(c).model_dump(mode="json"))


@router.patch("/{category_id}")
async def update_category(
    category_id: uuid.UUID,
    payload: CategoryUpdate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("category.manage")),
) -> dict:
    c = await CategoryRepository(db).get(category_id)
    if c is None:
        raise NotFoundError("Category not found.")
    for field, value in payload.model_dump(exclude_unset=True).items():
        if value is None and field != "is_active":
            continue
        setattr(c, field, value)
    await db.commit()
    return ok(CategoryPublic.model_validate(c).model_dump(mode="json"))


@router.delete("/{category_id}")
async def deactivate_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("category.manage")),
) -> dict:
    c = await CategoryRepository(db).get(category_id)
    if c is None:
        raise NotFoundError("Category not found.")
    c.is_active = False
    await db.commit()
    return ok(CategoryPublic.model_validate(c).model_dump(mode="json"))


@router.post("/{category_id}/restore")
async def restore_category(
    category_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("category.manage")),
) -> dict:
    c = await CategoryRepository(db).get(category_id)
    if c is None:
        raise NotFoundError("Category not found.")
    c.is_active = True
    await db.commit()
    return ok(CategoryPublic.model_validate(c).model_dump(mode="json"))
