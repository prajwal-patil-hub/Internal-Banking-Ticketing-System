"""InboundEmail model — raw emails received via IMAP before processing.

Stores the full email payload so we can reprocess on failure and maintain an
audit trail of all inbound support requests. EmailStatus tracks the processing
lifecycle from PENDING through PROCESSED / FAILED / SPAM / DUPLICATE.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class EmailStatus(str, enum.Enum):
    PENDING = "pending"
    PROCESSED = "processed"
    FAILED = "failed"
    SPAM = "spam"
    DUPLICATE = "duplicate"


class InboundEmail(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "inbound_emails"

    __table_args__ = (
        Index("ix_inbound_emails_message_id", "message_id"),
        Index("ix_inbound_emails_thread_id", "thread_id"),
        Index("ix_inbound_emails_received_at", "received_at"),
        Index("ix_inbound_emails_status", "status"),
    )

    # RFC 2822 Message-ID — unique per email
    message_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)

    # Headers
    from_address: Mapped[str] = mapped_column(String(255), nullable=False)
    to_address: Mapped[str] = mapped_column(String(255), nullable=False)
    cc_addresses: Mapped[list[str] | None] = mapped_column(ARRAY(String), nullable=True)
    subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Body
    body_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_html: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Timestamps
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Linked ticket
    ticket_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Processing state
    status: Mapped[str] = mapped_column(
        String(20), default=EmailStatus.PENDING.value, nullable=False
    )
    is_spam: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    spam_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_phishing: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    processing_error: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # Threading / reply detection
    is_reply: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    in_reply_to: Mapped[str | None] = mapped_column(String(255), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)

    # Attachment metadata
    attachments_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Email authentication
    spf_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    dkim_pass: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    sender_domain: Mapped[str | None] = mapped_column(String(255), nullable=True)
