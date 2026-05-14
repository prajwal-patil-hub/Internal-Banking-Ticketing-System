"""Ticket model — core entity of the ticketing system.

Covers the full lifecycle of a support ticket: creation, categorisation,
SLA tracking, AI enrichment, email threading and duplicate detection.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class TicketPriority(str, enum.Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TicketStatus(str, enum.Enum):
    NEW = "new"
    ACKNOWLEDGED = "acknowledged"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    ON_HOLD = "on_hold"
    ESCALATED = "escalated"
    RESOLVED = "resolved"
    CLOSED = "closed"
    REOPENED = "reopened"


class TicketSource(str, enum.Enum):
    EMAIL = "email"
    PORTAL = "portal"
    PHONE = "phone"
    CHAT = "chat"
    API = "api"


class TicketCategory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ticket_categories"

    code: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    department: Mapped[str] = mapped_column(String(100), nullable=False)
    banking_domain: Mapped[str] = mapped_column(String(50), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    subcategories: Mapped[list[TicketSubCategory]] = relationship(
        back_populates="category", lazy="selectin"
    )


class TicketSubCategory(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "ticket_subcategories"

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(String(30), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    category: Mapped[TicketCategory] = relationship(
        back_populates="subcategories", lazy="selectin"
    )


class Ticket(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "tickets"

    __table_args__ = (
        Index("ix_tickets_status", "status"),
        Index("ix_tickets_priority", "priority"),
        Index("ix_tickets_reporter_id", "reporter_id"),
        Index("ix_tickets_assignee_id", "assignee_id"),
        Index("ix_tickets_branch_id", "branch_id"),
        Index("ix_tickets_created_at", "created_at"),
        Index("ix_tickets_email_message_id", "email_message_id"),
    )

    # Core identity
    ticket_number: Mapped[str] = mapped_column(
        String(20), unique=True, index=True, nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Status / priority / source
    status: Mapped[TicketStatus] = mapped_column(
        Enum(TicketStatus, name="ticketstatus"),
        default=TicketStatus.NEW,
        nullable=False,
    )
    priority: Mapped[TicketPriority] = mapped_column(
        Enum(TicketPriority, name="ticketpriority"),
        default=TicketPriority.MEDIUM,
        nullable=False,
    )
    source: Mapped[TicketSource] = mapped_column(
        Enum(TicketSource, name="ticketsource"),
        default=TicketSource.PORTAL,
        nullable=False,
    )

    # Categorisation
    category_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    subcategory_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_subcategories.id", ondelete="SET NULL"),
        nullable=True,
    )

    # People
    reporter_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    assignee_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Branch / department
    branch_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("branches.id", ondelete="SET NULL"),
        nullable=True,
    )
    department: Mapped[str | None] = mapped_column(String(100), nullable=True)

    # Tags
    tags: Mapped[list[str] | None] = mapped_column(
        ARRAY(String), nullable=True, default=None
    )

    # AI enrichment
    ai_category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_subcategory: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ai_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    ai_risk_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    ai_routing_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ai_sentiment: Mapped[str | None] = mapped_column(String(20), nullable=True)

    # Email threading
    email_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_from: Mapped[str | None] = mapped_column(String(255), nullable=True)
    email_subject: Mapped[str | None] = mapped_column(String(500), nullable=True)

    # SLA
    sla_policy_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("sla_policies.id", ondelete="SET NULL"),
        nullable=True,
    )
    response_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolution_due_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    sla_breached: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    sla_paused_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Timestamps
    first_response_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    resolved_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Duplicate detection
    duplicate_of_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("tickets.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Internal notes
    internal_notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    category: Mapped[TicketCategory | None] = relationship(
        foreign_keys=[category_id], lazy="selectin"
    )
    subcategory: Mapped[TicketSubCategory | None] = relationship(
        foreign_keys=[subcategory_id], lazy="selectin"
    )
    reporter: Mapped[User] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[reporter_id], lazy="selectin"
    )
    assignee: Mapped[User | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[assignee_id], lazy="selectin"
    )
    comments: Mapped[list[TicketComment]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="ticket", lazy="selectin", cascade="all, delete-orphan"
    )
    attachments: Mapped[list[Attachment]] = relationship(  # type: ignore[name-defined]  # noqa: F821
        back_populates="ticket", lazy="selectin", cascade="all, delete-orphan"
    )
    duplicate_of: Mapped[Ticket | None] = relationship(
        foreign_keys=[duplicate_of_id], remote_side="Ticket.id", lazy="selectin"
    )
