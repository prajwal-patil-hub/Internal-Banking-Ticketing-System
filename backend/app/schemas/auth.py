"""Auth DTOs (request/response)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    # Plain str (not EmailStr) — login is a credential check, not a
    # registration form. Strict EmailStr rejects valid intranet TLDs like
    # `.local`, which doesn't add security and breaks legitimate logins.
    email: str = Field(min_length=3, max_length=255)
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


class UserPublic(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    role: str
    branch_id: uuid.UUID | None
    mfa_enabled: bool

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserPublic
    tokens: TokenPair
