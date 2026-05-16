"""TicketComment model — messages attached to a ticket.

Internal comments are visible only to agents/supervisors. AI-generated
comments are flagged for auditability.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Index, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class CommentSource(str, enum.Enum):
    EMAIL = "email"
    AGENT = "agent"
    AI = "ai"
    SYSTEM = "system"


class TicketComment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ticket_comments"

    __table_args__ = (Index("ix_ticket_comments_ticket_id", "ticket_id"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    body: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source: Mapped[CommentSource] = mapped_column(
        Enum(
            CommentSource,
            name="commentsource",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=CommentSource.AGENT,
        nullable=False,
    )
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    ticket: Mapped["Ticket"] = relationship(  # type: ignore[name-defined]
        back_populates="comments", lazy="selectin"
    )
    author: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[author_id], lazy="selectin"
    )
