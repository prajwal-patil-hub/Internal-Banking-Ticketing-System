from __future__ import annotations

import uuid

from pydantic import BaseModel, Field


class CategoryCreate(BaseModel):
    name: str = Field(min_length=2, max_length=100)
    description: str = Field(default="", max_length=255)
    default_priority: str = Field(default="medium")


class CategoryPublic(BaseModel):
    id: uuid.UUID
    name: str
    description: str
    default_priority: str
    is_active: bool

    model_config = {"from_attributes": True}
