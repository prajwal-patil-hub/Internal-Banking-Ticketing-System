"""Category and subcategory management API routes.

Read operations are open to all authenticated users. Write operations
(create/update) are restricted to admins only.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.ticket import TicketCategory, TicketSubCategory
from app.models.user import User
from app.schemas.envelope import ok

log = get_logger(__name__)

router = APIRouter(prefix="/categories", tags=["categories"])


# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_category(cat: TicketCategory, *, include_subcategories: bool = True) -> dict:
    base = {
        "id": str(cat.id),
        "code": cat.code,
        "name": cat.name,
        "department": cat.department,
        "banking_domain": cat.banking_domain,
        "description": cat.description,
        "is_active": cat.is_active,
        "created_at": cat.created_at.isoformat(),
        "updated_at": cat.updated_at.isoformat(),
    }
    if include_subcategories:
        base["subcategories"] = [_serialize_subcategory(s) for s in cat.subcategories]
    return base


def _serialize_subcategory(sub: TicketSubCategory) -> dict:
    return {
        "id": str(sub.id),
        "category_id": str(sub.category_id),
        "code": sub.code,
        "name": sub.name,
        "description": sub.description,
        "is_active": sub.is_active,
        "created_at": sub.created_at.isoformat(),
        "updated_at": sub.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", summary="List all active categories")
async def list_categories(
    request: Request,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    stmt = select(TicketCategory)
    if not include_inactive:
        stmt = stmt.where(TicketCategory.is_active == True)  # noqa: E712
    stmt = stmt.order_by(TicketCategory.name.asc())
    result = await db.execute(stmt)
    categories = result.scalars().all()
    return ok([_serialize_category(c) for c in categories])


@router.post(
    "",
    status_code=status.HTTP_201_CREATED,
    summary="Create a new category (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def create_category(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    code = payload.get("code", "").strip().lower()
    name = payload.get("name", "").strip()
    department = payload.get("department", "").strip()
    banking_domain = payload.get("banking_domain", "").strip()

    if not code:
        raise ValidationError("code is required.")
    if not name:
        raise ValidationError("name is required.")
    if not department:
        raise ValidationError("department is required.")
    if not banking_domain:
        raise ValidationError("banking_domain is required.")

    # Check uniqueness of code
    existing = await db.execute(select(TicketCategory).where(TicketCategory.code == code))
    if existing.scalar_one_or_none() is not None:
        raise ConflictError(f"Category with code '{code}' already exists.")

    category = TicketCategory(
        code=code,
        name=name,
        department=department,
        banking_domain=banking_domain,
        description=payload.get("description", ""),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    log.info("category_created", category_id=str(category.id), code=code, user_id=str(current_user.id))
    return ok(_serialize_category(category))


@router.get("/{category_id}", summary="Get category with subcategories")
async def get_category(
    category_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError(f"Category {category_id} not found.")
    return ok(_serialize_category(category, include_subcategories=True))


@router.patch(
    "/{category_id}",
    summary="Update a category (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def update_category(
    category_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    category = result.scalar_one_or_none()
    if category is None:
        raise NotFoundError(f"Category {category_id} not found.")

    if "name" in payload:
        category.name = payload["name"]
    if "department" in payload:
        category.department = payload["department"]
    if "banking_domain" in payload:
        category.banking_domain = payload["banking_domain"]
    if "description" in payload:
        category.description = payload["description"]
    if "is_active" in payload:
        category.is_active = bool(payload["is_active"])
    if "code" in payload:
        new_code = payload["code"].strip().lower()
        if new_code != category.code:
            dup = await db.execute(select(TicketCategory).where(TicketCategory.code == new_code))
            if dup.scalar_one_or_none() is not None:
                raise ConflictError(f"Category code '{new_code}' already in use.")
            category.code = new_code

    await db.commit()
    await db.refresh(category)
    log.info("category_updated", category_id=str(category.id), user_id=str(current_user.id))
    return ok(_serialize_category(category))


@router.get("/{category_id}/subcategories", summary="List subcategories for a category")
async def list_subcategories(
    category_id: uuid.UUID,
    request: Request,
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Verify category exists
    cat_result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    if cat_result.scalar_one_or_none() is None:
        raise NotFoundError(f"Category {category_id} not found.")

    stmt = select(TicketSubCategory).where(TicketSubCategory.category_id == category_id)
    if not include_inactive:
        stmt = stmt.where(TicketSubCategory.is_active == True)  # noqa: E712
    stmt = stmt.order_by(TicketSubCategory.name.asc())
    result = await db.execute(stmt)
    subcategories = result.scalars().all()
    return ok([_serialize_subcategory(s) for s in subcategories])


@router.post(
    "/{category_id}/subcategories",
    status_code=status.HTTP_201_CREATED,
    summary="Create a subcategory (admin only)",
    dependencies=[Depends(require_roles("admin"))],
)
async def create_subcategory(
    category_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Verify parent category exists
    cat_result = await db.execute(select(TicketCategory).where(TicketCategory.id == category_id))
    if cat_result.scalar_one_or_none() is None:
        raise NotFoundError(f"Category {category_id} not found.")

    code = payload.get("code", "").strip().lower()
    name = payload.get("name", "").strip()

    if not code:
        raise ValidationError("code is required.")
    if not name:
        raise ValidationError("name is required.")

    # Unique code within category
    dup = await db.execute(
        select(TicketSubCategory).where(
            TicketSubCategory.category_id == category_id,
            TicketSubCategory.code == code,
        )
    )
    if dup.scalar_one_or_none() is not None:
        raise ConflictError(f"Subcategory code '{code}' already exists in this category.")

    subcategory = TicketSubCategory(
        category_id=category_id,
        code=code,
        name=name,
        description=payload.get("description", ""),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(subcategory)
    await db.commit()
    await db.refresh(subcategory)
    log.info("subcategory_created", subcategory_id=str(subcategory.id), category_id=str(category_id), user_id=str(current_user.id))
    return ok(_serialize_subcategory(subcategory))
