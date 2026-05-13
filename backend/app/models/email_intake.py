"""InboundEmail model — raw emails received via IMAP before processing.

Stores the full email payload so we can reprocess on failure and
maintain an audit trail of all inbound support requests.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class InboundEmail(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inbound_emails"

    __table_args__ = (
        Index("ix_inbound_emails_message_id", "message_id"),
        Index("ix_inbound_emails_processed", "is_processed"),
        Index("ix_inbound_emails_received_at", "received_at"),
    )

    # Email headers
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(500), nullable=False)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Body
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Raw payload for reprocessing
    raw_payload: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Processing state
    is_processed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    processing_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)

    # Created ticket
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
