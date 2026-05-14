"""SLA Policy and Tracking models.

SLAPolicy defines response/resolution targets per category+priority.
SLATracking records per-ticket SLA state, including pause/resume cycles
and breach notifications.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class SLAPolicy(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sla_policies"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # Matches TicketPriority enum values: critical|high|medium|low
    priority: Mapped[str] = mapped_column(String(20), nullable=False)
    response_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    resolution_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    business_hours_only: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_default: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    category: Mapped[TicketCategory | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[category_id], lazy="selectin"
    )


class SLATracking(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "sla_tracking"

    __table_args__ = (UniqueConstraint("ticket_id", name="uq_sla_tracking_ticket"),)

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sla_policies.id", ondelete="SET NULL"),
        nullable=True,
    )

    response_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    resolution_due_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    is_response_breached: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    is_resolution_breached: Mapped[bool] = mapped_column(
        Boolean, default=False, nullable=False
    )
    paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    total_paused_minutes: Mapped[int] = mapped_column(
        Integer, default=0, nullable=False
    )
    breach_notified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    policy: Mapped[SLAPolicy | None] = relationship(
        foreign_keys=[policy_id], lazy="selectin"
    )
