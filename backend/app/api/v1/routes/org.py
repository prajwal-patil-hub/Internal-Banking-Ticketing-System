"""Org hierarchy management: HierarchyLevels, OrgUnits, OrgRoles."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.models.org import HierarchyLevel, OrgRole, OrgUnit
from app.models.user import User
from app.schemas.envelope import ok, paginated
from app.services.org_service import get_hierarchy_chain, get_subtree_ids

router = APIRouter(prefix="/org", tags=["org"])


# ---------------------------------------------------------------------------
# Hierarchy Levels
# ---------------------------------------------------------------------------

@router.get("/levels", summary="List hierarchy levels")
async def list_levels(
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(HierarchyLevel).order_by(HierarchyLevel.level_order)
    )
    levels = result.scalars().all()
    return ok([_serialize_level(lvl) for lvl in levels])


@router.post("/levels", status_code=status.HTTP_201_CREATED, summary="Create hierarchy level")
async def create_level(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    name = payload.get("name", "").strip()
    if not name:
        raise ValidationError("name is required.")
    level_order = payload.get("level_order")
    if level_order is None:
        raise ValidationError("level_order is required.")
    lvl = HierarchyLevel(name=name, level_order=int(level_order), is_active=payload.get("is_active", True))
    db.add(lvl)
    await db.commit()
    await db.refresh(lvl)
    return ok(_serialize_level(lvl))


@router.patch("/levels/{level_id}", summary="Update hierarchy level")
async def update_level(
    level_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    lvl = await _get_level_or_404(level_id, db)
    if "name" in payload:
        lvl.name = payload["name"]
    if "level_order" in payload:
        lvl.level_order = int(payload["level_order"])
    if "is_active" in payload:
        lvl.is_active = bool(payload["is_active"])
    await db.commit()
    await db.refresh(lvl)
    return ok(_serialize_level(lvl))


@router.delete("/levels/{level_id}")
async def delete_level(
    level_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> Response:
    lvl = await _get_level_or_404(level_id, db)
    result = await db.execute(select(OrgUnit.id).where(OrgUnit.hierarchy_level_id == level_id).limit(1))
    if result.scalar_one_or_none():
        raise ConflictError("Cannot delete level with associated org units.")
    await db.delete(lvl)
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Org Units
# ---------------------------------------------------------------------------

@router.get("/units", summary="List org units")
async def list_units(
    hierarchy_level_id: Annotated[uuid.UUID | None, Query()] = None,
    parent_id: Annotated[uuid.UUID | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=200)] = 50,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func, or_
    stmt = select(OrgUnit).where(OrgUnit.is_active.is_(True))
    if hierarchy_level_id:
        stmt = stmt.where(OrgUnit.hierarchy_level_id == hierarchy_level_id)
    if parent_id:
        stmt = stmt.where(OrgUnit.parent_id == parent_id)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(or_(OrgUnit.name.ilike(term), OrgUnit.code.ilike(term)))
    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()
    stmt = stmt.order_by(OrgUnit.name).offset((page - 1) * per_page).limit(per_page)
    units = (await db.execute(stmt)).scalars().all()
    return paginated([_serialize_unit(u) for u in units], page=page, size=per_page, total=total)


@router.get("/units/{unit_id}", summary="Get org unit")
async def get_unit(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    unit = await _get_unit_or_404(unit_id, db)
    chain = await get_hierarchy_chain(db, unit_id)
    data = _serialize_unit(unit)
    data["hierarchy_chain"] = chain
    return ok(data)


@router.post("/units", status_code=status.HTTP_201_CREATED, summary="Create org unit")
async def create_unit(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    name = payload.get("name", "").strip()
    code = payload.get("code", "").strip().upper()
    hierarchy_level_id = payload.get("hierarchy_level_id")
    if not name or not code or not hierarchy_level_id:
        raise ValidationError("name, code, and hierarchy_level_id are required.")
    # Check code uniqueness
    existing = await db.execute(select(OrgUnit.id).where(OrgUnit.code == code))
    if existing.scalar_one_or_none():
        raise ConflictError(f"Org unit code '{code}' already exists.")
    unit = OrgUnit(
        hierarchy_level_id=uuid.UUID(str(hierarchy_level_id)),
        parent_id=uuid.UUID(str(payload["parent_id"])) if payload.get("parent_id") else None,
        name=name,
        code=code,
        address=payload.get("address"),
        contact_email=payload.get("contact_email"),
        contact_phone=payload.get("contact_phone"),
        is_active=payload.get("is_active", True),
    )
    db.add(unit)
    await db.commit()
    await db.refresh(unit)
    return ok(_serialize_unit(unit))


@router.patch("/units/{unit_id}", summary="Update org unit")
async def update_unit(
    unit_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    unit = await _get_unit_or_404(unit_id, db)
    for field in ("name", "address", "contact_email", "contact_phone"):
        if field in payload:
            setattr(unit, field, payload[field])
    if "is_active" in payload:
        unit.is_active = bool(payload["is_active"])
    if "parent_id" in payload:
        unit.parent_id = uuid.UUID(str(payload["parent_id"])) if payload["parent_id"] else None
    await db.commit()
    await db.refresh(unit)
    return ok(_serialize_unit(unit))


@router.delete("/units/{unit_id}")
async def delete_unit(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> Response:
    unit = await _get_unit_or_404(unit_id, db)
    unit.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/units/{unit_id}/subtree", summary="Get all unit IDs in subtree")
async def get_unit_subtree(
    unit_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    ids = await get_subtree_ids(db, unit_id)
    return ok({"unit_id": str(unit_id), "subtree_ids": [str(i) for i in ids]})


# ---------------------------------------------------------------------------
# Org Roles
# ---------------------------------------------------------------------------

@router.get("/roles", summary="List org roles")
async def list_org_roles(
    hierarchy_level_id: Annotated[uuid.UUID | None, Query()] = None,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(get_current_user),
) -> dict:
    stmt = select(OrgRole).where(OrgRole.is_active.is_(True))
    if hierarchy_level_id:
        stmt = stmt.where(OrgRole.hierarchy_level_id == hierarchy_level_id)
    stmt = stmt.order_by(OrgRole.hierarchy_level_id, OrgRole.role_order)
    roles = (await db.execute(stmt)).scalars().all()
    return ok([_serialize_org_role(r) for r in roles])


@router.post("/roles", status_code=status.HTTP_201_CREATED, summary="Create org role")
async def create_org_role(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    name = payload.get("name", "").strip()
    hierarchy_level_id = payload.get("hierarchy_level_id")
    if not name or not hierarchy_level_id:
        raise ValidationError("name and hierarchy_level_id are required.")
    role = OrgRole(
        hierarchy_level_id=uuid.UUID(str(hierarchy_level_id)),
        name=name,
        role_order=int(payload.get("role_order", 0)),
        can_manage_unit=bool(payload.get("can_manage_unit", False)),
        can_manage_subtree=bool(payload.get("can_manage_subtree", False)),
        is_active=payload.get("is_active", True),
    )
    db.add(role)
    await db.commit()
    await db.refresh(role)
    return ok(_serialize_org_role(role))


@router.patch("/roles/{role_id}", summary="Update org role")
async def update_org_role(
    role_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    result = await db.execute(select(OrgRole).where(OrgRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise NotFoundError(f"OrgRole {role_id} not found.")
    for field in ("name", "role_order", "can_manage_unit", "can_manage_subtree", "is_active"):
        if field in payload:
            setattr(role, field, payload[field])
    await db.commit()
    await db.refresh(role)
    return ok(_serialize_org_role(role))


@router.delete("/roles/{role_id}")
async def delete_org_role(
    role_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> Response:
    result = await db.execute(select(OrgRole).where(OrgRole.id == role_id))
    role = result.scalar_one_or_none()
    if not role:
        raise NotFoundError(f"OrgRole {role_id} not found.")
    role.is_active = False
    await db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _serialize_level(lvl: HierarchyLevel) -> dict:
    return {
        "id": str(lvl.id),
        "name": lvl.name,
        "level_order": lvl.level_order,
        "is_active": lvl.is_active,
        "created_at": lvl.created_at.isoformat(),
        "updated_at": lvl.updated_at.isoformat(),
    }


def _serialize_unit(u: OrgUnit) -> dict:
    return {
        "id": str(u.id),
        "hierarchy_level_id": str(u.hierarchy_level_id),
        "hierarchy_level": u.hierarchy_level.name if u.hierarchy_level else None,
        "parent_id": str(u.parent_id) if u.parent_id else None,
        "parent_name": u.parent.name if u.parent else None,
        "name": u.name,
        "code": u.code,
        "address": u.address,
        "contact_email": u.contact_email,
        "contact_phone": u.contact_phone,
        "is_active": u.is_active,
        "created_at": u.created_at.isoformat(),
        "updated_at": u.updated_at.isoformat(),
    }


def _serialize_org_role(r: OrgRole) -> dict:
    return {
        "id": str(r.id),
        "hierarchy_level_id": str(r.hierarchy_level_id),
        "hierarchy_level": r.hierarchy_level.name if r.hierarchy_level else None,
        "name": r.name,
        "role_order": r.role_order,
        "can_manage_unit": r.can_manage_unit,
        "can_manage_subtree": r.can_manage_subtree,
        "is_active": r.is_active,
        "created_at": r.created_at.isoformat(),
        "updated_at": r.updated_at.isoformat(),
    }


async def _get_level_or_404(level_id: uuid.UUID, db: AsyncSession) -> HierarchyLevel:
    result = await db.execute(select(HierarchyLevel).where(HierarchyLevel.id == level_id))
    lvl = result.scalar_one_or_none()
    if not lvl:
        raise NotFoundError(f"HierarchyLevel {level_id} not found.")
    return lvl


async def _get_unit_or_404(unit_id: uuid.UUID, db: AsyncSession) -> OrgUnit:
    result = await db.execute(select(OrgUnit).where(OrgUnit.id == unit_id))
    unit = result.scalar_one_or_none()
    if not unit:
        raise NotFoundError(f"OrgUnit {unit_id} not found.")
    return unit
