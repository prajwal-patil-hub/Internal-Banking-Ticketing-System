"""Authentication endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session
from app.repositories.user_repo import (
    LoginAttemptRepository,
    RefreshTokenRepository,
    UserRepository,
)
from app.schemas.auth import (
    LoginRequest,
    LoginResponse,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserPublic,
)
from app.schemas.envelope import ok
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
                    "org_unit_id": user.org_unit_id,
                    "org_unit": {
                        "id": user.org_unit.id,
                        "name": user.org_unit.name,
                        "code": user.org_unit.code,
                        "level": user.org_unit.hierarchy_level.name if user.org_unit.hierarchy_level else None,
                    } if user.org_unit else None,
                    "org_role_id": user.org_role_id,
                    "org_role": {
                        "id": user.org_role.id,
                        "name": user.org_role.name,
                        "can_manage_unit": user.org_role.can_manage_unit,
                        "can_manage_subtree": user.org_role.can_manage_subtree,
                    } if user.org_role else None,
                    "is_super_admin": user.is_super_admin,
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
