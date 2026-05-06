"""sla — first-response tracking columns

Revision ID: 0007_first_response_sla
Revises: 0006_audit_immutable
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0007_first_response_sla"
down_revision: Union[str, None] = "0006_audit_immutable"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "sla_tracking",
        sa.Column("response_due_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "sla_tracking",
        sa.Column("response_breached", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "sla_tracking",
        sa.Column("response_breach_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_sla_tracking_response_due_at", "sla_tracking", ["response_due_at"])
    op.create_index("ix_sla_tracking_response_breached", "sla_tracking", ["response_breached"])


def downgrade() -> None:
    op.drop_index("ix_sla_tracking_response_breached", table_name="sla_tracking")
    op.drop_index("ix_sla_tracking_response_due_at", table_name="sla_tracking")
    op.drop_column("sla_tracking", "response_breach_at")
    op.drop_column("sla_tracking", "response_breached")
    op.drop_column("sla_tracking", "response_due_at")
