"""Branch operational fields: status, manager, capacity.

Branch was a P1 placeholder carrying only `is_active`. The Branch Management
screen needs to show whether a branch is actually serving customers, who runs
it, and how close to capacity it is running — none of which `is_active` can
express: a decommissioned branch is inactive, a branch with a dead ATM is
active but degraded.

Revision ID: 0004_branch_operations
Revises: 0003_org_hierarchy
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0004_branch_operations"
down_revision: Union[str, None] = "0003_org_hierarchy"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS = sa.Enum(
    "operational", "maintenance", "incident", name="branchstatus"
)


def upgrade() -> None:
    _STATUS.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "branches",
        sa.Column(
            "status", _STATUS, nullable=False, server_default="operational"
        ),
    )
    op.add_column(
        "branches",
        sa.Column("status_note", sa.String(length=255), nullable=False, server_default=""),
    )
    op.add_column(
        "branches",
        sa.Column("manager_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.add_column(
        "branches",
        sa.Column("ticket_capacity", sa.Integer(), nullable=False, server_default="20"),
    )
    op.create_foreign_key(
        "fk_branches_manager_id_users",
        "branches", "users",
        ["manager_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_branches_status", "branches", ["status"])
    op.create_index("ix_branches_region", "branches", ["region"])


def downgrade() -> None:
    op.drop_index("ix_branches_region", table_name="branches")
    op.drop_index("ix_branches_status", table_name="branches")
    op.drop_constraint("fk_branches_manager_id_users", "branches", type_="foreignkey")
    op.drop_column("branches", "ticket_capacity")
    op.drop_column("branches", "manager_id")
    op.drop_column("branches", "status_note")
    op.drop_column("branches", "status")
    _STATUS.drop(op.get_bind(), checkfirst=True)
