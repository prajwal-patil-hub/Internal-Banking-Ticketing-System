"""Escalation models — rules and event log.

EscalationRule defines when and to whom a ticket should be escalated.
EscalationEvent records every escalation that fires, for audit and
SLA compliance reporting.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class EscalationTrigger(str, enum.Enum):
    SLA_BREACH = "sla_breach"
    MANUAL = "manual"
    HIGH_RISK = "high_risk"
    VIP_CUSTOMER = "vip_customer"
    REGULATORY = "regulatory"


class EscalationRule(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "escalation_rules"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    trigger: Mapped[EscalationTrigger] = mapped_column(
        Enum(
            EscalationTrigger,
            name="escalationtrigger",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    trigger_after_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    escalate_to_role: Mapped[str] = mapped_column(String(50), nullable=False)
    escalate_to_user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    notify_email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Minimum priority level that triggers this rule (e.g. "high" = high + critical)
    priority_threshold: Mapped[str | None] = mapped_column(String(20), nullable=True)

    escalate_to_user: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[escalate_to_user_id], lazy="selectin"
    )
    category: Mapped["TicketCategory | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[category_id], lazy="selectin"
    )


class EscalationEvent(UUIDPKMixin, Base):
    __tablename__ = "escalation_events"

    ticket_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    rule_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("escalation_rules.id", ondelete="SET NULL"),
        nullable=True,
    )
    trigger: Mapped[EscalationTrigger] = mapped_column(
        Enum(
            EscalationTrigger,
            name="escalationtrigger",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    triggered_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    escalated_to_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    escalated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    rule: Mapped["EscalationRule | None"] = relationship(
        foreign_keys=[rule_id], lazy="selectin"
    )
    escalated_to: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[escalated_to_id], lazy="selectin"
    )
    escalated_by: Mapped["User | None"] = relationship(  # type: ignore[name-defined]
        foreign_keys=[escalated_by_id], lazy="selectin"
    )
