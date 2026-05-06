from __future__ import annotations

import uuid
from datetime import datetime

from pydantic import BaseModel


class SLAPolicyPublic(BaseModel):
    id: uuid.UUID
    priority: str
    response_minutes: int
    resolution_minutes: int

    model_config = {"from_attributes": True}


class SLATrackingPublic(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    policy_priority: str
    due_at: datetime
    breached: bool
    breach_at: datetime | None
    paused_at: datetime | None
    total_paused_seconds: int

    model_config = {"from_attributes": True}
