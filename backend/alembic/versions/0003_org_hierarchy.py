"""Org hierarchy: HierarchyLevel, OrgUnit, OrgRole, TicketSequence; extend users and tickets.

Revision ID: 0003_org_hierarchy
Revises: 0002_tickets_ai_email
Create Date: 2026-08-08
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_org_hierarchy"
down_revision: Union[str, None] = "0002_tickets_ai_email"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # hierarchy_levels
    # ------------------------------------------------------------------
    op.create_table(
        "hierarchy_levels",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(100), nullable=False, unique=True),
        sa.Column("level_order", sa.Integer, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ------------------------------------------------------------------
    # org_units
    # ------------------------------------------------------------------
    op.create_table(
        "org_units",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hierarchy_level_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("code", sa.String(30), nullable=False, unique=True),
        sa.Column("address", sa.String(500), nullable=True),
        sa.Column("contact_email", sa.String(255), nullable=True),
        sa.Column("contact_phone", sa.String(30), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["hierarchy_level_id"], ["hierarchy_levels.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["parent_id"], ["org_units.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_org_units_code", "org_units", ["code"], unique=True)
    op.create_index("ix_org_units_hierarchy_level_id", "org_units", ["hierarchy_level_id"])
    op.create_index("ix_org_units_parent_id", "org_units", ["parent_id"])

    # ------------------------------------------------------------------
    # org_roles
    # ------------------------------------------------------------------
    op.create_table(
        "org_roles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("hierarchy_level_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("role_order", sa.Integer, nullable=False, server_default="0"),
        sa.Column("can_manage_unit", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("can_manage_subtree", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(["hierarchy_level_id"], ["hierarchy_levels.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("hierarchy_level_id", "name", name="uq_org_role_level_name"),
    )
    op.create_index("ix_org_roles_hierarchy_level_id", "org_roles", ["hierarchy_level_id"])

    # ------------------------------------------------------------------
    # ticket_sequences
    # ------------------------------------------------------------------
    op.create_table(
        "ticket_sequences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("org_unit_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("year", sa.Integer, nullable=False),
        sa.Column("last_seq", sa.Integer, nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["org_unit_id"], ["org_units.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("org_unit_id", "year", name="uq_ticket_seq_unit_year"),
    )

    # ------------------------------------------------------------------
    # Extend users table
    # ------------------------------------------------------------------
    op.add_column("users", sa.Column(
        "org_unit_id", postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column("users", sa.Column(
        "org_role_id", postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column("users", sa.Column(
        "is_super_admin", sa.Boolean, nullable=False, server_default=sa.false()
    ))
    op.create_foreign_key(
        "fk_users_org_unit_id", "users", "org_units", ["org_unit_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_users_org_role_id", "users", "org_roles", ["org_role_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_users_org_unit_id", "users", ["org_unit_id"])
    op.create_index("ix_users_org_role_id", "users", ["org_role_id"])

    # ------------------------------------------------------------------
    # Extend tickets table
    # ------------------------------------------------------------------
    op.add_column("tickets", sa.Column(
        "org_unit_id", postgresql.UUID(as_uuid=True), nullable=True
    ))
    op.add_column("tickets", sa.Column(
        "reopen_count", sa.Integer, nullable=False, server_default="0"
    ))
    op.create_foreign_key(
        "fk_tickets_org_unit_id", "tickets", "org_units", ["org_unit_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_tickets_org_unit_id", "tickets", ["org_unit_id"])
    op.alter_column("tickets", "ticket_number", type_=sa.String(50))

    # ------------------------------------------------------------------
    # Seed default hierarchy levels
    # ------------------------------------------------------------------
    op.execute("""
        INSERT INTO hierarchy_levels (id, name, level_order, is_active, created_at, updated_at)
        VALUES
            (gen_random_uuid(), 'Branch',          1, true, now(), now()),
            (gen_random_uuid(), 'Regional Office', 2, true, now(), now()),
            (gen_random_uuid(), 'Circle Office',   3, true, now(), now()),
            (gen_random_uuid(), 'Head Office',     4, true, now(), now())
    """)

    # Seed default roles for each level
    op.execute("""
        INSERT INTO org_roles (id, hierarchy_level_id, name, role_order, can_manage_unit, can_manage_subtree, is_active, created_at, updated_at)
        SELECT gen_random_uuid(), hl.id, r.name, r.role_order, r.can_manage_unit, r.can_manage_subtree, true, now(), now()
        FROM hierarchy_levels hl
        CROSS JOIN (
            VALUES
                ('Staff',        0, false, false),
                ('Officer',      1, false, false),
                ('Head',         2, true,  false),
                ('Admin',        3, true,  true)
        ) AS r(name, role_order, can_manage_unit, can_manage_subtree)
    """)


def downgrade() -> None:
    # Revert tickets
    op.drop_index("ix_tickets_org_unit_id", table_name="tickets")
    op.drop_constraint("fk_tickets_org_unit_id", "tickets", type_="foreignkey")
    op.drop_column("tickets", "reopen_count")
    op.drop_column("tickets", "org_unit_id")
    op.alter_column("tickets", "ticket_number", type_=sa.String(20))

    # Revert users
    op.drop_index("ix_users_org_role_id", table_name="users")
    op.drop_index("ix_users_org_unit_id", table_name="users")
    op.drop_constraint("fk_users_org_role_id", "users", type_="foreignkey")
    op.drop_constraint("fk_users_org_unit_id", "users", type_="foreignkey")
    op.drop_column("users", "is_super_admin")
    op.drop_column("users", "org_role_id")
    op.drop_column("users", "org_unit_id")

    # Drop new tables (reverse order)
    op.drop_table("ticket_sequences")
    op.drop_index("ix_org_roles_hierarchy_level_id", table_name="org_roles")
    op.drop_table("org_roles")
    op.drop_index("ix_org_units_parent_id", table_name="org_units")
    op.drop_index("ix_org_units_hierarchy_level_id", table_name="org_units")
    op.drop_index("ix_org_units_code", table_name="org_units")
    op.drop_table("org_units")
    op.drop_table("hierarchy_levels")
