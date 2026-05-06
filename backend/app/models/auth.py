"""Auth-related side tables.

- RefreshToken: server-side store of refresh-token *hashes* (never the raw
  token). Rotated on every use; old tokens are revoked. Theft of a refresh
  token is detectable: if a revoked token is presented, we revoke the whole
  user chain.

- LoginAttempt: brute-force defence + audit telemetry.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, UUIDPKMixin


class RefreshToken(UUIDPKMixin, Base):
    __tablename__ = "refresh_tokens"

    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, index=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    replaced_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(64), default="", nullable=False)
    user_agent: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.utcnow()


class LoginAttempt(UUIDPKMixin, Base):
    __tablename__ = "login_attempts"

    email: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    ip_address: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    success: Mapped[bool] = mapped_column(Boolean, nullable=False)
    attempted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    user_agent: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    reason: Mapped[str] = mapped_column(String(80), default="", nullable=False)
