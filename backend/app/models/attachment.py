"""Attachment model — files uploaded to a ticket.

Tracks S3 storage location, malware scan results, PII detection, and
optional OCR text extraction for searchability.
"""

from __future__ import annotations

import uuid

from sqlalchemy import BigInteger, Boolean, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class Attachment(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "attachments"

    __table_args__ = (Index("ix_attachments_ticket_id", "ticket_id"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
    )
    uploader_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # File metadata
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # S3 storage
    s3_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(100), nullable=False)

    # Integrity & security
    checksum_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    is_malware_scanned: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_clean: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # PII & classification
    has_pii_detected: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    ocr_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    document_type: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Relationships
    ticket: Mapped["Ticket"] = relationship(  # type: ignore[name-defined]
        back_populates="attachments", lazy="selectin"
    )
    uploader: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[uploader_id], lazy="selectin"
    )
