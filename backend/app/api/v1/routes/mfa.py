"""MFA (TOTP) enrolment + verify.

Flow:
  1. authenticated user calls POST /mfa/enroll  -> returns base32 secret + otpauth URI (for QR)
  2. user pastes a code from their authenticator into POST /mfa/verify
  3. on success, mfa_enabled is set to True

Login MFA enforcement (admin/supervisor/auditor) is implemented by
AuthService at next login: if `mfa_enabled` is True, the login response
returns a short-lived MFA challenge instead of the full token pair.
"""

from __future__ import annotations

import pyotp
from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.config import settings
from app.core.exceptions import ConflictError, ValidationError
from app.models.user import User
from app.schemas.envelope import ok

router = APIRouter(prefix="/mfa", tags=["mfa"])


class VerifyRequest(BaseModel):
    code: str = Field(min_length=6, max_length=6)


@router.post("/enroll")
async def enroll(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    if user.mfa_enabled:
        raise ConflictError("MFA already enabled. Disable first to re-enrol.")
    secret = pyotp.random_base32()
    user.mfa_secret = secret
    await db.commit()

    issuer = settings.APP_NAME
    uri = pyotp.totp.TOTP(secret).provisioning_uri(name=user.email, issuer_name=issuer)
    return ok({"secret": secret, "otpauth_uri": uri})


@router.post("/verify")
async def verify(
    payload: VerifyRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    if not user.mfa_secret:
        raise ValidationError("Start with /mfa/enroll first.")
    totp = pyotp.TOTP(user.mfa_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise ValidationError("Invalid TOTP code.")
    user.mfa_enabled = True
    await db.commit()
    return ok({"mfa_enabled": True})


@router.post("/disable")
async def disable(
    payload: VerifyRequest,
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    if not user.mfa_enabled or not user.mfa_secret:
        return ok({"mfa_enabled": False})
    if not pyotp.TOTP(user.mfa_secret).verify(payload.code, valid_window=1):
        raise ValidationError("Invalid TOTP code.")
    user.mfa_enabled = False
    user.mfa_secret = None
    await db.commit()
    return ok({"mfa_enabled": False})
