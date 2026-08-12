"""Branch model — a physical bank branch.

Started life as a P1 placeholder holding just enough for the User.branch_id FK
to resolve. The operational fields below back the Branch Management screen:
somewhere to see which branches are up, who runs them, and how loaded they are.
"""

from __future__ import annotations

import enum
import uuid

from sqlalchemy import Boolean, Enum, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDPKMixin


class BranchStatus(str, enum.Enum):
    """Whether the branch is serving customers normally.

    Distinct from `is_active`, which is a lifecycle flag — a decommissioned
    branch is inactive; a branch with a broken ATM is active but degraded.
    """

    OPERATIONAL = "operational"
    MAINTENANCE = "maintenance"
    INCIDENT = "incident"


class Branch(UUIDPKMixin, TimestampMixin, Base):
    __tablename__ = "branches"

    code: Mapped[str] = mapped_column(String(20), unique=True, index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    region: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    address: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    ifsc: Mapped[str] = mapped_column(String(20), default="", nullable=False)
    contact_email: Mapped[str] = mapped_column(String(255), default="", nullable=False)
    contact_phone: Mapped[str] = mapped_column(String(40), default="", nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    status: Mapped[BranchStatus] = mapped_column(
        Enum(BranchStatus, name="branchstatus", values_callable=lambda x: [e.value for e in x]),
        default=BranchStatus.OPERATIONAL,
        nullable=False,
    )
    #: Note explaining a non-operational status ("ATM offline since 06:00").
    status_note: Mapped[str] = mapped_column(String(255), default="", nullable=False)

    manager_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    #: Open tickets this branch is staffed to carry. Drives the load bar, so a
    #: branch running hot is visible before its SLAs start slipping.
    ticket_capacity: Mapped[int] = mapped_column(Integer, default=20, nullable=False)

    manager: Mapped[User | None] = relationship(  # type: ignore[name-defined]  # noqa: F821
        foreign_keys=[manager_id], lazy="selectin"
    )
