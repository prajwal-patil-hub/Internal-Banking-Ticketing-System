from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, EmailStr, Field


class BranchCreate(BaseModel):
    code: str = Field(min_length=2, max_length=20)
    name: str = Field(min_length=2, max_length=150)
    region: str = Field(default="", max_length=100)
    address: str = Field(default="", max_length=255)
    ifsc: str = Field(default="", max_length=20)
    contact_email: EmailStr | str = Field(default="")
    contact_phone: str = Field(default="", max_length=40)


class BranchPublic(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    region: str
    address: str
    ifsc: str
    contact_email: str
    contact_phone: str
    is_active: bool
    created_at: datetime

    model_config = {"from_attributes": True}
