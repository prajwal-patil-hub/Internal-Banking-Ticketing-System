"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.exceptions import AuthenticationError
from app.core.security import hash_password, verify_password
from app.models.user import User
from app.repositories.user_repo import (
    LoginAttemptRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import (
    ChangePasswordRequest,
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
)
from app.schemas.envelope import ok
from app.services.audit_service import AuditService
from app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(db: AsyncSession) -> AuthService:
    return AuthService(
        UserRepository(db),
        RefreshTokenRepository(db),
        LoginAttemptRepository(db),
    )


@router.post("/login")
async def login(
    payload: LoginRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    user, access, access_exp, refresh, refresh_exp = await _service(db).login(
        email=payload.email,
        password=payload.password,
        ip=request.state.client_ip,
        user_agent=request.state.user_agent,
    )
    await db.commit()
    return ok(
        LoginResponse(
            user=UserPublic.model_validate(
                {
                    "id": user.id,
                    "email": user.email,
                    "full_name": user.full_name,
                    "role": user.role.name,
                    "branch_id": user.branch_id,
                    "mfa_enabled": user.mfa_enabled,
                }
            ),
            tokens=TokenPair(
                access_token=access,
                access_expires_at=access_exp,
                refresh_token=refresh,
                refresh_expires_at=refresh_exp,
            ),
        ).model_dump(mode="json"),
    )


@router.post("/refresh")
async def refresh(
    payload: RefreshRequest,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    _, access, access_exp, new_refresh, refresh_exp = await _service(db).refresh(
        raw_token=payload.refresh_token,
        ip=request.state.client_ip,
        user_agent=request.state.user_agent,
    )
    await db.commit()
    return ok(
        TokenPair(
            access_token=access,
            access_expires_at=access_exp,
            refresh_token=new_refresh,
            refresh_expires_at=refresh_exp,
        ).model_dump(mode="json"),
    )


@router.post("/logout")
async def logout(
    payload: LogoutRequest,
    db: AsyncSession = Depends(get_session),
) -> dict:
    await _service(db).logout(raw_token=payload.refresh_token)
    await db.commit()
    return ok({"logged_out": True})


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    """Self-service password change. Requires the current password.
    Revokes all of this user's other refresh tokens (defense-in-depth)."""
    if not verify_password(payload.current_password, user.password_hash):
        raise AuthenticationError("Current password is incorrect.")
    if payload.new_password == payload.current_password:
        raise AuthenticationError("New password must differ from the current one.")

    user.password_hash = hash_password(payload.new_password)
    user.failed_login_count = 0
    user.locked_until = None

    await RefreshTokenRepository(db).revoke_all_for_user(user.id)

    await AuditService(db).log(
        actor=user,
        entity_type="user",
        entity_id=user.id,
        action="user.password_changed",
        new_value={"by": "self"},
    )
    await db.commit()
    return ok({"changed": True})
