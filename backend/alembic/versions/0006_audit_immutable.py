"""audit_logs (append-only) — table + immutability trigger

Revision ID: 0006_audit_immutable
Revises: 0005_escalations_notifications
Create Date: 2026-05-06

Banking-grade auditing requires that audit rows cannot be modified or
deleted, even by administrators. We enforce that with a BEFORE UPDATE OR
DELETE trigger that raises an exception. In production deployments the
DB role used by the API is also granted only INSERT and SELECT on this
table — see infra notes.
"""
from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_audit_immutable"
down_revision: Union[str, None] = "0005_escalations_notifications"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "audit_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True),
                  sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("actor_role", sa.String(50), nullable=False, server_default=""),
        sa.Column("entity_type", sa.String(50), nullable=False),
        sa.Column("entity_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("action", sa.String(100), nullable=False),
        sa.Column("old_value", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("new_value", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("ip_address", sa.String(64), nullable=False, server_default=""),
        sa.Column("user_agent", sa.String(255), nullable=False, server_default=""),
        sa.Column("request_id", sa.String(64), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_audit_logs_actor_user_id", "audit_logs", ["actor_user_id"])
    op.create_index("ix_audit_logs_entity_type", "audit_logs", ["entity_type"])
    op.create_index("ix_audit_logs_entity_id", "audit_logs", ["entity_id"])
    op.create_index("ix_audit_logs_action", "audit_logs", ["action"])
    op.create_index("ix_audit_logs_created_at", "audit_logs", ["created_at"])

    # Immutability trigger: block UPDATE / DELETE.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_immutable()
        RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'audit_logs is append-only';
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_update
        BEFORE UPDATE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
        """
    )
    op.execute(
        """
        CREATE TRIGGER trg_audit_logs_no_delete
        BEFORE DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_delete ON audit_logs;")
    op.execute("DROP TRIGGER IF EXISTS trg_audit_logs_no_update ON audit_logs;")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_immutable();")
    for ix in (
        "ix_audit_logs_created_at", "ix_audit_logs_action", "ix_audit_logs_entity_id",
        "ix_audit_logs_entity_type", "ix_audit_logs_actor_user_id",
    ):
        op.drop_index(ix, table_name="audit_logs")
    op.drop_table("audit_logs")
