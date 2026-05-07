"""Auth DTOs (request/response)."""

from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    password: str = Field(min_length=8, max_length=200)


class RefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=10)


class LogoutRequest(BaseModel):
    refresh_token: str | None = None


class ChangePasswordRequest(BaseModel):
    current_password: str = Field(min_length=8, max_length=200)
    new_password: str = Field(min_length=8, max_length=200)


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
    is_active: bool = True

    model_config = {"from_attributes": True}


class LoginResponse(BaseModel):
    user: UserPublic
    tokens: TokenPair


class UserCreate(BaseModel):
    email: str = Field(min_length=3, max_length=255)
    full_name: str = Field(min_length=2, max_length=150)
    role: str = Field(min_length=2, max_length=50)
    branch_id: uuid.UUID | None = None
    # If omitted the server generates one and returns it once.
    password: str | None = Field(default=None, min_length=8, max_length=200)


class UserUpdate(BaseModel):
    full_name: str | None = Field(default=None, min_length=2, max_length=150)
    role: str | None = Field(default=None, min_length=2, max_length=50)
    branch_id: uuid.UUID | None = None
    is_active: bool | None = None


class PasswordResetResponse(BaseModel):
    user: UserPublic
    new_password: str
