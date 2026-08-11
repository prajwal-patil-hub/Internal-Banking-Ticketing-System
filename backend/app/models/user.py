"""User model."""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class User(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    full_name: Mapped[str] = mapped_column(String(150), nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    role_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("roles.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    # Org hierarchy fields
    org_unit_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    org_role_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_roles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_super_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mfa_secret: Mapped[str | None] = mapped_column(String(64), nullable=True)
    mfa_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failed_login_count: Mapped[int] = mapped_column(default=0, nullable=False)
    locked_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    # Forward references: SQLAlchemy resolves these by name when the mappers
    # are configured, so importing the classes here would only create a cycle.
    role: Mapped[Role] = relationship(  # type: ignore[name-defined]  # noqa: F821
        lazy="selectin",
    )
    org_unit: Mapped[OrgUnit | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[org_unit_id], lazy="selectin",
    )
    org_role: Mapped[OrgRole | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[org_role_id], lazy="selectin",
    )
