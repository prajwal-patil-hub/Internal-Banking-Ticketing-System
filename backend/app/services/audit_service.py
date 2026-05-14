"""Audit service — write-once audit trail for every significant system event.

Every entry is immutable by design: no UPDATE is ever issued against
audit_logs. Indexed for fast retrieval by entity, actor, action, and time.
"""

from __future__ import annotations

import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.models.audit import AuditAction, AuditLog

log = get_logger(__name__)


class AuditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def log(
        self,
        *,
        entity_type: str,
        entity_id: str | None,
        action: AuditAction,
        actor_id: str | None,
        actor_email: str | None = None,
        actor_role: str | None = None,
        old_values: dict | None = None,
        new_values: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
        request_id: str | None = None,
        metadata: dict | None = None,
    ) -> AuditLog:
        """Create an immutable audit log entry and flush it to the session."""
        actor_uuid: uuid.UUID | None = None
        if actor_id is not None:
            try:
                actor_uuid = uuid.UUID(actor_id)
            except ValueError:
                log.warning("audit.bad_actor_id", actor_id=actor_id)

        entry = AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=actor_uuid,
            actor_email=actor_email,
            actor_role=actor_role,
            old_values=old_values,
            new_values=new_values,
            ip_address=ip_address,
            user_agent=user_agent,
            request_id=request_id,
            metadata_=metadata,
        )
        self.db.add(entry)
        await self.db.flush()
        log.info(
            "audit.logged",
            entity_type=entity_type,
            entity_id=entity_id,
            action=action.value,
            actor_id=str(actor_id),
        )
        return entry

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_audit_trail(
        self,
        *,
        entity_type: str | None = None,
        entity_id: str | None = None,
        actor_id: str | None = None,
        action: str | None = None,
        page: int = 1,
        per_page: int = 50,
    ) -> tuple[list[AuditLog], int]:
        """Return a paginated audit trail with optional filters."""
        stmt = select(AuditLog)

        if entity_type is not None:
            stmt = stmt.where(AuditLog.entity_type == entity_type)
        if entity_id is not None:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        if actor_id is not None:
            try:
                actor_uuid = uuid.UUID(actor_id)
                stmt = stmt.where(AuditLog.actor_id == actor_uuid)
            except ValueError:
                pass
        if action is not None:
            try:
                audit_action = AuditAction(action)
                stmt = stmt.where(AuditLog.action == audit_action)
            except ValueError:
                pass

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total: int = (await self.db.execute(count_stmt)).scalar_one()

        offset = (page - 1) * per_page
        stmt = stmt.order_by(AuditLog.created_at.desc()).offset(offset).limit(per_page)
        rows = (await self.db.execute(stmt)).scalars().all()
        return list(rows), total
