"""Org hierarchy models: HierarchyLevel, OrgUnit, OrgRole, TicketSequence."""

from __future__ import annotations

import uuid

from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class HierarchyLevel(UUIDPKMixin, TimestampMixin, Base):
    """Configurable level in the org hierarchy (e.g. Branch, Regional Office, Circle Office)."""

    __tablename__ = "hierarchy_levels"

    name: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    level_order: Mapped[int] = mapped_column(Integer, nullable=False)  # 1=lowest (Branch), N=highest (HO)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    org_units: Mapped[list[OrgUnit]] = relationship(back_populates="hierarchy_level")
    org_roles: Mapped[list[OrgRole]] = relationship(back_populates="hierarchy_level")


class OrgUnit(UUIDPKMixin, TimestampMixin, Base):
    """An org unit (branch, regional office, circle office, head office, etc.)."""

    __tablename__ = "org_units"

    hierarchy_level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hierarchy_levels.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    parent_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_units.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False, index=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(30), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    hierarchy_level: Mapped[HierarchyLevel] = relationship(back_populates="org_units", lazy="selectin")
    parent: Mapped[OrgUnit | None] = relationship(
        foreign_keys=[parent_id], remote_side="OrgUnit.id", lazy="selectin"
    )
    children: Mapped[list[OrgUnit]] = relationship(
        foreign_keys=[parent_id], back_populates="parent"
    )


class OrgRole(UUIDPKMixin, TimestampMixin, Base):
    """A role that exists at a specific hierarchy level (e.g. Teller at Branch level)."""

    __tablename__ = "org_roles"

    hierarchy_level_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("hierarchy_levels.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    role_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    can_manage_unit: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    can_manage_subtree: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    __table_args__ = (UniqueConstraint("hierarchy_level_id", "name", name="uq_org_role_level_name"),)

    hierarchy_level: Mapped[HierarchyLevel] = relationship(back_populates="org_roles", lazy="selectin")


class TicketSequence(UUIDPKMixin, Base):
    """Per-org-unit per-year atomic sequence counter for ticket numbering."""

    __tablename__ = "ticket_sequences"

    org_unit_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("org_units.id", ondelete="CASCADE"),
        nullable=False,
    )
    year: Mapped[int] = mapped_column(Integer, nullable=False)
    last_seq: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    __table_args__ = (UniqueConstraint("org_unit_id", "year", name="uq_ticket_seq_unit_year"),)
