"""Single-use MFA recovery codes."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class MFABackupCode(UUIDPKMixin, TimestampMixin, Base):
    """One recovery code. Stored hashed; usable once.

    A spent code is marked rather than deleted, so "a recovery code was used at
    09:14" remains answerable — which is exactly the sort of question asked
    after an account is compromised.
    """

    __tablename__ = "mfa_backup_codes"

    __table_args__ = (
        Index("ix_mfa_backup_codes_user_id", "user_id"),
        UniqueConstraint("user_id", "code_hash", name="uq_mfa_backup_codes_user_hash"),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    code_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
