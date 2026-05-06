from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from pydantic import BaseModel


class AuditLogPublic(BaseModel):
    id: uuid.UUID
    actor_user_id: uuid.UUID | None
    actor_role: str
    entity_type: str
    entity_id: uuid.UUID | None
    action: str
    old_value: dict[str, Any]
    new_value: dict[str, Any]
    ip_address: str
    user_agent: str
    request_id: str
    created_at: datetime

    model_config = {"from_attributes": True}
