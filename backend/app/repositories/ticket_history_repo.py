"""Data access for assignments, comments, attachments."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ticket_history import Attachment, TicketAssignment, TicketComment


class TicketAssignmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, a: TicketAssignment) -> TicketAssignment:
        self.db.add(a)
        await self.db.flush()
        return a

    async def close_open_for(self, ticket_id: uuid.UUID) -> None:
        stmt = select(TicketAssignment).where(
            TicketAssignment.ticket_id == ticket_id,
            TicketAssignment.unassigned_at.is_(None),
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        now = datetime.now(timezone.utc)
        for r in rows:
            r.unassigned_at = now

    async def list_for(self, ticket_id: uuid.UUID) -> list[TicketAssignment]:
        stmt = (
            select(TicketAssignment)
            .where(TicketAssignment.ticket_id == ticket_id)
            .order_by(TicketAssignment.assigned_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())


class TicketCommentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, c: TicketComment) -> TicketComment:
        self.db.add(c)
        await self.db.flush()
        return c

    async def list_for(
        self, ticket_id: uuid.UUID, *, include_internal: bool
    ) -> list[TicketComment]:
        stmt = (
            select(TicketComment)
            .where(TicketComment.ticket_id == ticket_id)
            .order_by(TicketComment.created_at.asc())
        )
        if not include_internal:
            stmt = stmt.where(TicketComment.is_internal.is_(False))
        return list((await self.db.execute(stmt)).scalars().all())


class AttachmentRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def add(self, a: Attachment) -> Attachment:
        self.db.add(a)
        await self.db.flush()
        return a

    async def get(self, attachment_id: uuid.UUID) -> Attachment | None:
        return await self.db.get(Attachment, attachment_id)

    async def list_for(self, ticket_id: uuid.UUID) -> list[Attachment]:
        stmt = (
            select(Attachment)
            .where(Attachment.ticket_id == ticket_id)
            .order_by(Attachment.created_at.desc())
        )
        return list((await self.db.execute(stmt)).scalars().all())
