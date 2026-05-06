"""ticket workflow — assignments, comments, attachments

Revision ID: 0003_ticket_workflow
Revises: 0002_core_domain
Create Date: 2026-05-06
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_ticket_workflow"
down_revision: Union[str, None] = "0002_core_domain"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ticket_assignments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("assigned_to_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_to_team_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("assigned_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("assigned_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("unassigned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.String(255), nullable=False, server_default=""),
    )
    op.create_index("ix_ticket_assignments_ticket_id", "ticket_assignments", ["ticket_id"])
    op.create_index("ix_ticket_assignments_assigned_to_user_id", "ticket_assignments", ["assigned_to_user_id"])
    op.create_index("ix_ticket_assignments_assigned_to_team_id", "ticket_assignments", ["assigned_to_team_id"])

    op.create_table(
        "ticket_comments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("author_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("is_internal", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ticket_comments_ticket_id", "ticket_comments", ["ticket_id"])
    op.create_index("ix_ticket_comments_author_id", "ticket_comments", ["author_id"])

    op.create_table(
        "attachments",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("ticket_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("tickets.id", ondelete="CASCADE"), nullable=False),
        sa.Column("comment_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("ticket_comments.id", ondelete="SET NULL"), nullable=True),
        sa.Column("uploaded_by", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("file_name", sa.String(255), nullable=False),
        sa.Column("mime_type", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("storage_key", sa.String(512), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_attachments_ticket_id", "attachments", ["ticket_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_ticket_id", table_name="attachments")
    op.drop_table("attachments")
    op.drop_index("ix_ticket_comments_author_id", table_name="ticket_comments")
    op.drop_index("ix_ticket_comments_ticket_id", table_name="ticket_comments")
    op.drop_table("ticket_comments")
    op.drop_index("ix_ticket_assignments_assigned_to_team_id", table_name="ticket_assignments")
    op.drop_index("ix_ticket_assignments_assigned_to_user_id", table_name="ticket_assignments")
    op.drop_index("ix_ticket_assignments_ticket_id", table_name="ticket_assignments")
    op.drop_table("ticket_assignments")
