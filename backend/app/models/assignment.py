"""Assignment configuration: category routing rules and tunable settings.

Both exist because auto-assignment stopped being a fixed behaviour and became
something the bank operates: supervisors decide who owns a category, admins
decide how long an unassigned ticket may sit before the system steps in.
"""

from __future__ import annotations

import uuid

from sqlalchemy import ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class AssignmentRule(UUIDPKMixin, TimestampMixin, Base):
    """"Tickets in this category go to this person" — a preference, not a law.

    Routing consults the rule first and falls through to the normal
    branch-then-workload search whenever the named person is on leave,
    deactivated, or no longer holds a role that can be assigned work. A rule
    that silently parks tickets on someone unavailable would be worse than no
    rule at all.

    One rule per category, so there is never a question of which one won.
    """

    __tablename__ = "assignment_rules"
    __table_args__ = (
        UniqueConstraint("category_id", name="uq_assignment_rules_category"),
    )

    category_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ticket_categories.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    assignee_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    note: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )

    category: Mapped[TicketCategory] = relationship(  # type: ignore[name-defined]  # noqa: F821
        lazy="selectin",
    )
    assignee: Mapped[User] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[assignee_id], lazy="selectin",
    )


class SystemSetting(TimestampMixin, Base):
    """A small key/value store for values an administrator may change at runtime.

    Deliberately not environment variables: the auto-assign delay is an
    operational decision a bank will want to change without a redeploy, and it
    needs an audit trail of who changed it.
    """

    __tablename__ = "system_settings"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )


#: How long a ticket may sit unassigned before the safety net assigns it.
#: Auto-assignment is a supervisor's decision; this only stops a ticket raised
#: overnight from burning its whole SLA and then escalating to nobody.
AUTO_ASSIGN_DELAY_HOURS = "auto_assign_delay_hours"

#: Used when the row is absent. Two hours is long enough that a supervisor on
#: shift decides who works the ticket, and short enough that an out-of-hours
#: ticket is still owned well before a same-day SLA expires.
AUTO_ASSIGN_DELAY_HOURS_DEFAULT = 2.0
