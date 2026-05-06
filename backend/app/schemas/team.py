from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class TeamCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=255)
    supervisor_id: uuid.UUID | None = None


class TeamPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    supervisor_id: uuid.UUID | None
    is_active: bool

    model_config = {"from_attributes": True}
