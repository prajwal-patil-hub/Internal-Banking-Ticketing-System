"""Authentication endpoints."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.exceptions import AuthenticationError, ValidationError
from app.core.logging import get_logger
from app.core.security import (
    decode_token,
    generate_backup_codes,
    generate_mfa_secret,
    hash_backup_code,
    mfa_provisioning_uri,
    mfa_qr_svg,
    verify_password,
    verify_totp,
)
from app.models.mfa import MFABackupCode
from app.models.user import User
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

log = get_logger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])


def _service(db: AsyncSession) -> AuthService:
    return AuthService(
        UserRepository(db),
        RefreshTokenRepository(db),
        LoginAttemptRepository(db),
    )


def _public_user(user: User) -> dict:
    """Shape a User for UserPublic. Shared by the direct and post-MFA logins."""
    return {
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
        mfa_code=payload.mfa_code,
    )
    await db.commit()
    return ok(
        LoginResponse(
            user=UserPublic.model_validate(_public_user(user)),
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


# ---------------------------------------------------------------------------
# Multi-factor authentication (TOTP)
# ---------------------------------------------------------------------------
#
# Enrolment is two-step on purpose: /mfa/setup stores a secret but leaves MFA
# off, and only a correct code at /mfa/enable turns it on. A one-step enable
# would lock out anyone whose authenticator failed to scan the QR.

@router.post("/mfa/setup", summary="Begin MFA enrolment — returns a secret and QR URI")
async def mfa_setup(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if current_user.mfa_enabled:
        raise ValidationError(
            "Multi-factor authentication is already enabled. Disable it first to re-enrol."
        )

    secret = generate_mfa_secret()
    current_user.mfa_secret = secret
    current_user.mfa_enabled = False
    await db.commit()

    uri = mfa_provisioning_uri(secret, current_user.email)
    log.info("mfa_setup_started", user_id=str(current_user.id))
    return ok({
        "secret": secret,
        "otpauth_uri": uri,
        "qr_svg": mfa_qr_svg(uri),  # null if the QR library is unavailable
        "issuer": "SUCCESS Bank",
        "account": current_user.email,
    })


@router.post("/mfa/enable", summary="Confirm a code and switch MFA on")
async def mfa_enable(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    code = str(payload.get("code", "")).strip()
    if not code:
        raise ValidationError("code is required.")
    if not current_user.mfa_secret:
        raise ValidationError("Start enrolment with /auth/mfa/setup first.")
    if not verify_totp(current_user.mfa_secret, code):
        raise ValidationError("That code is not valid. Check your authenticator and try again.")

    current_user.mfa_enabled = True

    # Recovery codes are shown exactly once, here. Only their hashes are kept,
    # so there is no way to re-display them later — which is the property that
    # makes them safe to store at all.
    await db.execute(
        delete(MFABackupCode).where(MFABackupCode.user_id == current_user.id)
    )
    codes = generate_backup_codes()
    for code in codes:
        db.add(MFABackupCode(
            id=uuid.uuid4(),
            user_id=current_user.id,
            code_hash=hash_backup_code(code),
        ))
    await db.commit()

    log.info("mfa_enabled", user_id=str(current_user.id), backup_codes=len(codes))
    return ok({
        "mfa_enabled": True,
        "backup_codes": codes,
        "backup_codes_notice": (
            "Save these now — each works once and they cannot be shown again."
        ),
    })



@router.get("/mfa/backup-codes", summary="How many recovery codes remain")
async def mfa_backup_code_status(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    rows = (await db.execute(
        select(MFABackupCode).where(MFABackupCode.user_id == current_user.id)
    )).scalars().all()
    remaining = sum(1 for r in rows if r.used_at is None)
    return ok({
        "total": len(rows),
        "remaining": remaining,
        "used": len(rows) - remaining,
        # The codes themselves are unrecoverable by design — only hashes exist.
        "can_regenerate": current_user.mfa_enabled,
    })


@router.post("/mfa/backup-codes/regenerate", summary="Issue a fresh set of recovery codes")
async def regenerate_backup_codes(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace every code with a new set.

    Requires the password: regenerating invalidates the codes the real owner
    may be holding, so a hijacked session must not be able to do it quietly.
    """
    password = str(payload.get("password", ""))
    if not password or not verify_password(password, current_user.password_hash):
        raise AuthenticationError("Password is incorrect.")
    if not current_user.mfa_enabled:
        raise ValidationError("Two-factor authentication is not enabled.")

    await db.execute(
        delete(MFABackupCode).where(MFABackupCode.user_id == current_user.id)
    )
    codes = generate_backup_codes()
    for code in codes:
        db.add(MFABackupCode(
            id=uuid.uuid4(),
            user_id=current_user.id,
            code_hash=hash_backup_code(code),
        ))
    await db.commit()

    log.info("mfa_backup_codes_regenerated", user_id=str(current_user.id))
    return ok({"backup_codes": codes})

@router.post("/mfa/disable", summary="Turn MFA off (requires the account password)")
async def mfa_disable(
    payload: dict,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Password, not just a live session: otherwise a stolen access token is
    # enough to strip the second factor off the account.
    password = str(payload.get("password", ""))
    if not password or not verify_password(password, current_user.password_hash):
        raise AuthenticationError("Password is incorrect.")

    current_user.mfa_enabled = False
    current_user.mfa_secret = None
    await db.execute(
        delete(MFABackupCode).where(MFABackupCode.user_id == current_user.id)
    )
    await db.commit()

    log.info("mfa_disabled", user_id=str(current_user.id))
    return ok({"mfa_enabled": False})


@router.post("/mfa/verify", summary="Complete a login by answering the MFA challenge")
async def mfa_verify(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Exchange a challenge token plus a valid code for a real token pair."""
    mfa_token = str(payload.get("mfa_token", "")).strip()
    code = str(payload.get("code", "")).strip()
    if not mfa_token or not code:
        raise ValidationError("mfa_token and code are required.")

    try:
        claims = decode_token(mfa_token)
    except Exception as exc:
        raise AuthenticationError("This login attempt expired. Please sign in again.") from exc

    if claims.get("type") != "mfa":
        raise AuthenticationError("Wrong token type for this step.")

    user = await UserRepository(db).get_by_id(claims.get("sub", ""))
    if user is None or not user.is_active:
        raise AuthenticationError("Account unavailable.")
    if not user.mfa_enabled or not user.mfa_secret:
        raise ValidationError("Multi-factor authentication is not enabled for this account.")

    # Re-enter login so the lockout counters and audit trail behave identically
    # whether or not the account carries a second factor.
    user, access, access_exp, refresh_raw, refresh_exp = await _service(db).login_verified(
        user=user,
        code=code,
        ip=request.state.client_ip,
        user_agent=request.state.user_agent,
    )
    await db.commit()

    return ok(
        LoginResponse(
            user=UserPublic.model_validate(_public_user(user)),
            tokens=TokenPair(
                access_token=access,
                access_expires_at=access_exp,
                refresh_token=refresh_raw,
                refresh_expires_at=refresh_exp,
            ),
        ).model_dump(mode="json"),
    )
