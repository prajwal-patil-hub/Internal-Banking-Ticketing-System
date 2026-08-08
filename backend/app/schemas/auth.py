"""Auth DTOs (request/response)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class TokenPair(BaseModel):
    access_token: str
    access_expires_at: datetime
    refresh_token: str
    refresh_expires_at: datetime
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
    email: EmailStr
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
