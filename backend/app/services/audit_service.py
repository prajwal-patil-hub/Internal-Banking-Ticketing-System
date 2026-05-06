"""Audit service.

Exactly one chokepoint to write audit_logs. All callers go through this
so the schema and required fields stay enforced in code, not docs.

Context (ip, user_agent, request_id) is read off the FastAPI Request via
the audit context contextvar — see middleware/audit_context.py.
"""

from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.middleware.audit_context import current_audit_context
from app.models.audit import AuditLog
from app.models.user import User
from app.repositories.audit_repo import AuditRepository


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = AuditRepository(db)

    async def log(
        self,
        *,
        actor: User | None,
        entity_type: str,
        entity_id: uuid.UUID | None,
        action: str,
        old_value: dict[str, Any] | None = None,
        new_value: dict[str, Any] | None = None,
    ) -> AuditLog:
        ctx = current_audit_context()
        a = AuditLog(
            actor_user_id=actor.id if actor else None,
            actor_role=actor.role.name if actor else "",
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            old_value=old_value or {},
            new_value=new_value or {},
            ip_address=ctx.get("ip", ""),
            user_agent=ctx.get("user_agent", "")[:255],
            request_id=ctx.get("request_id", ""),
        )
        return await self.repo.add(a)
