from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel, Field


class TicketCreate(BaseModel):
    branch_id: uuid.UUID
    category_id: uuid.UUID
    title: str = Field(min_length=3, max_length=200)
    description: str = Field(min_length=3, max_length=10_000)
    priority: str = Field(default="medium")  # critical|high|medium|low


class TicketPublic(BaseModel):
    id: uuid.UUID
    ticket_no: str
    branch_id: uuid.UUID
    raised_by: uuid.UUID
    category_id: uuid.UUID
    title: str
    description: str
    priority: str
    status: str
    sla_due_at: datetime | None
    first_response_at: datetime | None
    resolved_at: datetime | None
    closed_at: datetime | None
    reopened_count: int
    assigned_team_id: uuid.UUID | None
    assigned_user_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class TicketSummary(BaseModel):
    id: uuid.UUID
    ticket_no: str
    title: str
    branch_id: uuid.UUID
    priority: str
    status: str
    sla_due_at: datetime | None
    assigned_user_id: uuid.UUID | None
    created_at: datetime

    model_config = {"from_attributes": True}
