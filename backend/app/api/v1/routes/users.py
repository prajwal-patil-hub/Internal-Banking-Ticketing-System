"""User management API — full CRUD with org hierarchy assignment."""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.exceptions import AuthorizationError, ConflictError, NotFoundError, ValidationError
from app.models.org import OrgRole, OrgUnit
from app.models.role import Role
from app.models.user import User
from app.schemas.envelope import ok, paginated

router = APIRouter(prefix="/users", tags=["users"])


# ---------------------------------------------------------------------------
# Serializer
# ---------------------------------------------------------------------------

def _serialize_user(user: User) -> dict:
    return {
        "id": str(user.id),
        "email": user.email,
        "full_name": user.full_name,
        "role_id": str(user.role_id),
        "role": user.role.name if user.role else None,
        "branch_id": str(user.branch_id) if user.branch_id else None,
        "org_unit_id": str(user.org_unit_id) if user.org_unit_id else None,
        "org_unit": {
            "id": str(user.org_unit.id),
            "name": user.org_unit.name,
            "code": user.org_unit.code,
            "level": user.org_unit.hierarchy_level.name if user.org_unit.hierarchy_level else None,
        } if user.org_unit else None,
        "org_role_id": str(user.org_role_id) if user.org_role_id else None,
        "org_role": {
            "id": str(user.org_role.id),
            "name": user.org_role.name,
            "can_manage_unit": user.org_role.can_manage_unit,
            "can_manage_subtree": user.org_role.can_manage_subtree,
        } if user.org_role else None,
        "is_super_admin": user.is_super_admin,
        "is_active": user.is_active,
        "mfa_enabled": user.mfa_enabled,
        "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
        "created_at": user.created_at.isoformat(),
        "updated_at": user.updated_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/me", summary="Get current user profile")
async def get_me(current_user: User = Depends(get_current_user)) -> dict:
    return ok(_serialize_user(current_user))


@router.get("", summary="List users (admin)")
async def list_users(
    org_unit_id: Annotated[uuid.UUID | None, Query()] = None,
    role: Annotated[str | None, Query()] = None,
    search: Annotated[str | None, Query(max_length=100)] = None,
    is_active: Annotated[bool | None, Query()] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=100)] = 20,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "supervisor")),
) -> dict:
    from sqlalchemy import or_
    stmt = select(User)
    if org_unit_id:
        stmt = stmt.where(User.org_unit_id == org_unit_id)
    if is_active is not None:
        stmt = stmt.where(User.is_active == is_active)
    if search:
        term = f"%{search}%"
        stmt = stmt.where(or_(User.full_name.ilike(term), User.email.ilike(term)))
    if role:
        from sqlalchemy import join
        stmt = stmt.join(Role, User.role_id == Role.id).where(Role.name == role)

    # Non-super-admins with org_unit scope see only users in their accessible subtree
    if not current_user.is_super_admin and current_user.org_unit_id:
        from app.services.org_service import get_accessible_org_unit_ids
        accessible = await get_accessible_org_unit_ids(current_user, db)
        if accessible is not None:
            stmt = stmt.where(User.org_unit_id.in_(accessible))

    total = (await db.execute(select(func.count()).select_from(stmt.subquery()))).scalar_one()
    stmt = stmt.order_by(User.full_name).offset((page - 1) * per_page).limit(per_page)
    users = (await db.execute(stmt)).scalars().all()
    return paginated([_serialize_user(u) for u in users], page=page, size=per_page, total=total)


@router.get("/{user_id}", summary="Get user by ID (admin)")
async def get_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "supervisor")),
) -> dict:
    user = await _get_user_or_404(user_id, db)
    return ok(_serialize_user(user))


@router.post("", status_code=status.HTTP_201_CREATED, summary="Create user (admin)")
async def create_user(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    _: User = Depends(require_roles("admin")),
) -> dict:
    from app.core.security import hash_password

    email = payload.get("email", "").strip().lower()
    full_name = payload.get("full_name", "").strip()
    password = payload.get("password", "")
    role_name = payload.get("role", "branch_user")

    if not email or not full_name or not password:
        raise ValidationError("email, full_name, and password are required.")
    if len(password) < 8:
        raise ValidationError("Password must be at least 8 characters.")

    # Check uniqueness
    existing = await db.execute(select(User.id).where(User.email == email))
    if existing.scalar_one_or_none():
        raise ConflictError(f"User with email '{email}' already exists.")

    # Resolve role
    role_result = await db.execute(select(Role).where(Role.name == role_name))
    role = role_result.scalar_one_or_none()
    if not role:
        raise ValidationError(f"Role '{role_name}' not found.")

    # Resolve org_unit
    org_unit_id = None
    if payload.get("org_unit_id"):
        org_unit_id = uuid.UUID(str(payload["org_unit_id"]))
        ou = await db.execute(select(OrgUnit.id).where(OrgUnit.id == org_unit_id))
        if not ou.scalar_one_or_none():
            raise ValidationError(f"OrgUnit '{org_unit_id}' not found.")

    # Resolve org_role
    org_role_id = None
    if payload.get("org_role_id"):
        org_role_id = uuid.UUID(str(payload["org_role_id"]))
        orole = await db.execute(select(OrgRole.id).where(OrgRole.id == org_role_id))
        if not orole.scalar_one_or_none():
            raise ValidationError(f"OrgRole '{org_role_id}' not found.")

    user = User(
        email=email,
        full_name=full_name,
        password_hash=hash_password(password),
        role_id=role.id,
        org_unit_id=org_unit_id,
        org_role_id=org_role_id,
        is_super_admin=bool(payload.get("is_super_admin", False)),
        is_active=bool(payload.get("is_active", True)),
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return ok(_serialize_user(user))


@router.patch("/{user_id}", summary="Update user (admin)")
async def update_user(
    user_id: uuid.UUID,
    payload: dict,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> dict:
    user = await _get_user_or_404(user_id, db)

    if "full_name" in payload:
        user.full_name = payload["full_name"]
    if "is_active" in payload:
        user.is_active = bool(payload["is_active"])
    if "is_super_admin" in payload and current_user.is_super_admin:
        user.is_super_admin = bool(payload["is_super_admin"])

    if "role" in payload:
        role_result = await db.execute(select(Role).where(Role.name == payload["role"]))
        role = role_result.scalar_one_or_none()
        if not role:
            raise ValidationError(f"Role '{payload['role']}' not found.")
        user.role_id = role.id

    if "org_unit_id" in payload:
        if payload["org_unit_id"]:
            org_unit_id = uuid.UUID(str(payload["org_unit_id"]))
            ou = await db.execute(select(OrgUnit.id).where(OrgUnit.id == org_unit_id))
            if not ou.scalar_one_or_none():
                raise ValidationError(f"OrgUnit '{org_unit_id}' not found.")
            user.org_unit_id = org_unit_id
        else:
            user.org_unit_id = None

    if "org_role_id" in payload:
        if payload["org_role_id"]:
            org_role_id = uuid.UUID(str(payload["org_role_id"]))
            orole = await db.execute(select(OrgRole.id).where(OrgRole.id == org_role_id))
            if not orole.scalar_one_or_none():
                raise ValidationError(f"OrgRole '{org_role_id}' not found.")
            user.org_role_id = org_role_id
        else:
            user.org_role_id = None

    if "password" in payload:
        from app.core.security import hash_password
        if len(payload["password"]) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        user.password_hash = hash_password(payload["password"])

    await db.commit()
    await db.refresh(user)
    return ok(_serialize_user(user))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin")),
) -> None:
    if str(user_id) == str(current_user.id):
        raise AuthorizationError("Cannot deactivate your own account.")
    user = await _get_user_or_404(user_id, db)
    user.is_active = False
    await db.commit()


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

async def _get_user_or_404(user_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError(f"User {user_id} not found.")
    return user
