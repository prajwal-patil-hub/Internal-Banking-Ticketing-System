"""User self-service + admin CRUD."""

from __future__ import annotations

import secrets
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.core.security import hash_password
from app.models.role import Role as RoleModel
from app.models.user import User
from app.repositories.user_repo import UserRepository
from app.schemas.auth import (
    PasswordResetResponse,
    UserCreate,
    UserPublic,
    UserUpdate,
)
from app.schemas.envelope import ok, paginated
from app.services.audit_service import AuditService
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/users", tags=["users"])


def _public(u: User) -> dict:
    return UserPublic.model_validate(
        {
            "id": u.id,
            "email": u.email,
            "full_name": u.full_name,
            "role": u.role.name if u.role else "",
            "branch_id": u.branch_id,
            "mfa_enabled": u.mfa_enabled,
            "is_active": u.is_active,
        }
    ).model_dump(mode="json")


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return ok(_public(user))


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
    return paginated([_public(u) for u in rows], page=p.page, size=p.size, total=total)


async def _resolve_role(db: AsyncSession, role_name: str) -> RoleModel:
    role = (
        await db.execute(select(RoleModel).where(RoleModel.name == role_name))
    ).scalar_one_or_none()
    if role is None:
        raise ValidationError("Unknown role.", details={"role": role_name})
    return role


@router.post("")
async def create_user(
    payload: UserCreate,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permissions("user.manage")),
) -> dict:
    repo = UserRepository(db)
    if await repo.get_by_email(payload.email.lower().strip()):
        raise ConflictError("A user with that email already exists.")
    role = await _resolve_role(db, payload.role)

    raw_password = payload.password or secrets.token_urlsafe(12)
    user = User(
        email=payload.email.lower().strip(),
        full_name=payload.full_name.strip(),
        password_hash=hash_password(raw_password),
        role_id=role.id,
        branch_id=payload.branch_id,
        is_active=True,
    )
    db.add(user)
    await db.flush()
    await AuditService(db).log(
        actor=actor,
        entity_type="user",
        entity_id=user.id,
        action="user.created",
        new_value={
            "email": user.email, "role": role.name,
            "branch_id": str(user.branch_id) if user.branch_id else None,
        },
    )
    await db.commit()
    # Refresh so .role relationship is loaded for the response.
    await db.refresh(user, attribute_names=["role"])

    response = _public(user)
    response_envelope = ok({"user": response, "initial_password": raw_password})
    return response_envelope


@router.patch("/{user_id}")
async def update_user(
    user_id: uuid.UUID,
    payload: UserUpdate,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permissions("user.manage")),
) -> dict:
    target = await UserRepository(db).get_by_id(user_id)
    if target is None:
        raise NotFoundError("User not found.")

    old = {
        "full_name": target.full_name, "role": target.role.name,
        "branch_id": str(target.branch_id) if target.branch_id else None,
        "is_active": target.is_active,
    }
    if payload.full_name is not None:
        target.full_name = payload.full_name.strip()
    if payload.role is not None:
        new_role = await _resolve_role(db, payload.role)
        target.role_id = new_role.id
    if "branch_id" in payload.model_fields_set:
        target.branch_id = payload.branch_id
    if payload.is_active is not None:
        target.is_active = payload.is_active

    await db.flush()
    await db.refresh(target, attribute_names=["role"])
    await AuditService(db).log(
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        action="user.updated",
        old_value=old,
        new_value={
            "full_name": target.full_name, "role": target.role.name,
            "branch_id": str(target.branch_id) if target.branch_id else None,
            "is_active": target.is_active,
        },
    )
    await db.commit()
    return ok(_public(target))


@router.delete("/{user_id}")
async def deactivate_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permissions("user.manage")),
) -> dict:
    """Soft delete: flips is_active=false. Hard delete is intentionally
    unavailable to preserve referential integrity with tickets and audit
    rows."""
    target = await UserRepository(db).get_by_id(user_id)
    if target is None:
        raise NotFoundError("User not found.")
    if target.id == actor.id:
        raise ConflictError("You cannot deactivate yourself.")
    target.is_active = False
    await db.flush()
    await db.refresh(target, attribute_names=["role"])
    await AuditService(db).log(
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        action="user.deactivated",
        new_value={"is_active": False},
    )
    await db.commit()
    return ok(_public(target))


@router.post("/{user_id}/restore")
async def restore_user(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permissions("user.manage")),
) -> dict:
    target = await UserRepository(db).get_by_id(user_id)
    if target is None:
        raise NotFoundError("User not found.")
    target.is_active = True
    await db.flush()
    await db.refresh(target, attribute_names=["role"])
    await AuditService(db).log(
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        action="user.restored",
        new_value={"is_active": True},
    )
    await db.commit()
    return ok(_public(target))


@router.post("/{user_id}/reset-password")
async def reset_password(
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    actor: User = Depends(require_permissions("user.manage")),
) -> dict:
    """Admin resets another user's password. Returns the new password
    once — the caller must surface it to the user via a side channel.
    Also revokes all of that user's refresh tokens so existing sessions
    must re-authenticate."""
    target = await UserRepository(db).get_by_id(user_id)
    if target is None:
        raise NotFoundError("User not found.")

    new_password = secrets.token_urlsafe(12)
    target.password_hash = hash_password(new_password)
    target.failed_login_count = 0
    target.locked_until = None

    # Best-effort revocation: blow away open refresh tokens for this user.
    from app.repositories.user_repo import RefreshTokenRepository
    await RefreshTokenRepository(db).revoke_all_for_user(target.id)

    await db.flush()
    await db.refresh(target, attribute_names=["role"])
    await AuditService(db).log(
        actor=actor,
        entity_type="user",
        entity_id=target.id,
        action="user.password_reset",
        new_value={"by": str(actor.id)},
    )
    await db.commit()
    return ok(
        PasswordResetResponse(
            user=UserPublic.model_validate(_public(target)),
            new_password=new_password,
        ).model_dump(mode="json")
    )
