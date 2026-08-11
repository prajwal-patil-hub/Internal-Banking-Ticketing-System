"""Auth DTOs (request/response)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str
    password: str = Field(min_length=8, max_length=200)
    #: Optional TOTP code, letting a client that already has one skip the
    #: separate challenge round-trip. Omit it and an MFA account replies with
    #: an MFA_REQUIRED challenge instead of tokens.
    mfa_code: str | None = Field(default=None, max_length=10)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
    #: The RFC 6750 scheme name, not a secret.
    token_type: str = "Bearer"


class OrgUnitPublic(BaseModel):
    id: uuid.UUID
    name: str
    code: str
    level: str | None = None

    model_config = {"from_attributes": True}


class OrgRolePublic(BaseModel):
    id: uuid.UUID
    name: str
    can_manage_unit: bool
    can_manage_subtree: bool

    model_config = {"from_attributes": True}


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    branch_id: uuid.UUID | None
    mfa_enabled: bool
    org_unit_id: uuid.UUID | None = None
    org_unit: OrgUnitPublic | None = None
    org_role_id: uuid.UUID | None = None
    org_role: OrgRolePublic | None = None
    is_super_admin: bool = False

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserPublic
    tokens: TokenPair
