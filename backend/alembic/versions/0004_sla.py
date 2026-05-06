"""sla policies + tracking

Revision ID: 0004_sla
Revises: 0003_ticket_workflow
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_sla"
down_revision: Union[str, None] = "0003_ticket_workflow"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "sla_policies",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("priority", sa.String(20), nullable=False, unique=True),
        sa.Column("response_minutes", sa.Integer, nullable=False),
        sa.Column("resolution_minutes", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "sla_tracking",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"),
                  nullable=False, unique=True),
        sa.Column("policy_priority", sa.String(20), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("breached", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("breach_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paused_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("total_paused_seconds", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_sla_tracking_ticket_id", "sla_tracking", ["ticket_id"], unique=True)
    op.create_index("ix_sla_tracking_due_at", "sla_tracking", ["due_at"])
    op.create_index("ix_sla_tracking_breached", "sla_tracking", ["breached"])


def downgrade() -> None:
    op.drop_index("ix_sla_tracking_breached", table_name="sla_tracking")
    op.drop_index("ix_sla_tracking_due_at", table_name="sla_tracking")
    op.drop_index("ix_sla_tracking_ticket_id", table_name="sla_tracking")
    op.drop_table("sla_tracking")
    op.drop_table("sla_policies")
