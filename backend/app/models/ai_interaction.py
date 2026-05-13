"""AI interaction models — chat sessions, messages, and raw interaction logs.

ChatSession groups a user's conversation with the AI assistant.
ChatMessage holds individual turns. AIInteractionLog captures every
raw API call for auditability, cost tracking, and debugging.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSON, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class ChatRole(str, enum.Enum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatSession(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "chat_sessions"

    __table_args__ = (Index("ix_chat_sessions_user_id", "user_id"),)

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Optionally linked to a specific ticket for context
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        lazy="selectin",
        cascade="all, delete-orphan",
        order_by="ChatMessage.created_at",
    )


class ChatMessage(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "chat_messages"

    __table_args__ = (Index("ix_chat_messages_session_id", "session_id"),)

    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[ChatRole] = mapped_column(
        Enum(ChatRole, name="chatrole"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    # Token usage for cost tracking
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)

    session: Mapped["ChatSession"] = relationship(
        back_populates="messages", lazy="selectin"
    )


class AIInteractionLog(UUIDPKMixin, TimestampMixin, Base):
    """Raw log of every AI API call — model, prompt, response, latency, cost."""

    __tablename__ = "ai_interaction_logs"

    __table_args__ = (
        Index("ix_ai_interaction_logs_ticket_id", "ticket_id"),
        Index("ix_ai_interaction_logs_user_id", "user_id"),
        Index("ix_ai_interaction_logs_interaction_type", "interaction_type"),
    )

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("chat_sessions.id", ondelete="SET NULL"),
        nullable=True,
    )

    interaction_type: Mapped[str] = mapped_column(
        String(50), nullable=False
    )  # categorize | summarize | suggest | chat | extract_email
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)

    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Structured result stored as JSON
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    confidence_score: Mapped[float | None] = mapped_column(Float, nullable=True)
