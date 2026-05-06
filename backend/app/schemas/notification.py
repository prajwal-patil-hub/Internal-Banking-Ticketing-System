from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class NotificationPublic(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    channel: str
    type: str
    subject: str
    body: str
    payload: dict[str, Any]
    status: str
    sent_at: datetime | None
    read_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class EscalationPublic(BaseModel):
    id: uuid.UUID
    ticket_id: uuid.UUID
    level: int
    escalated_to_user_id: uuid.UUID | None
    reason: str
    triggered_by_user_id: uuid.UUID | None
    is_automatic: bool
    escalated_at: datetime
    resolved_at: datetime | None

    model_config = {"from_attributes": True}
