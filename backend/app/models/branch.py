"""Branch model — placeholder fleshed out in P2.

Defined here in P1 so the User.branch_id FK can resolve at migration time.
"""

from __future__ import annotations

from sqlalchemy import Boolean, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, TimestampMixin, UUIDPKMixin


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
