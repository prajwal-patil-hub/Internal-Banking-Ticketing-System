from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class AssignRequest(BaseModel):
    user_id: uuid.UUID | None = None
    team_id: uuid.UUID | None = None
    reason: str = Field(default="", max_length=255)


class EscalateRequest(BaseModel):
    reason: str = Field(default="", max_length=1_000)


class ResolveRequest(BaseModel):
    notes: str = Field(default="", max_length=5_000)


class ReopenRequest(BaseModel):
    reason: str = Field(default="", max_length=1_000)


class CommentCreate(BaseModel):
    body: str = Field(min_length=1, max_length=10_000)
    is_internal: bool = False


class CommentPublic(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    author_id: uuid.UUID
    body: str
    is_internal: bool
    created_at: datetime

    model_config = {"from_attributes": True}


class AttachmentPublic(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    uploaded_by: uuid.UUID
    file_name: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    created_at: datetime

    model_config = {"from_attributes": True}


class AssignmentPublic(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    assigned_to_user_id: uuid.UUID | None
    assigned_to_team_id: uuid.UUID | None
    assigned_by: uuid.UUID
    assigned_at: datetime
    unassigned_at: datetime | None
    reason: str

    model_config = {"from_attributes": True}
