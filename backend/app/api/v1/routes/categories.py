from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.models.category import Category
from app.models.user import User
from app.repositories.category_repo import CategoryRepository
from app.schemas.category import CategoryCreate, CategoryPublic
from app.schemas.envelope import ok, paginated
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("")
async def list_categories(
    p: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    items, total = await CategoryRepository(db).list(offset=p.offset, limit=p.limit)
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
