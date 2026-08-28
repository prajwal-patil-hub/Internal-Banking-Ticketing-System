"""Put auto-assignment under human control: leave windows, category rules, tunable delay.

Three gaps this closes.

`users` had no notion of availability. The only flag routing could see was
`is_active`, which gates login — so the only way to stop sending work to
somebody on leave was to lock them out of the system. `leave_from`/`leave_to`
say nothing about access; they say "do not route new work here", and because
they are dates rather than a toggle they expire on their own. Nobody has to
remember to switch availability back on, which is the failure mode of every
manual on/off availability flag.

`assignment_rules` records the desk that owns a category — fraud disputes to
the fraud analyst — without making it mandatory. One rule per category, so
there is never a question of which rule won.

`system_settings` holds values an administrator changes while the system is
running. The auto-assign delay is an operational decision a bank will retune;
making it an environment variable would mean a redeploy and no record of who
changed it.

Revision ID: 0008_assignment_control
Revises: 0007_comment_attachments
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0008_assignment_control"
down_revision: Union[str, None] = "0007_comment_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- availability, which is not the same thing as an enabled account ----
    op.add_column("users", sa.Column("leave_from", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("leave_to", sa.Date(), nullable=True))
    op.add_column("users", sa.Column("leave_note", sa.String(length=200), nullable=True))
    # Routing filters on "is today inside the window", so the range is the index.
    op.create_index("ix_users_leave_window", "users", ["leave_from", "leave_to"])

    # --- optional category -> assignee preference ---------------------------
    op.create_table(
        "assignment_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("category_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("assignee_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("note", sa.String(length=200), nullable=True),
        sa.Column("created_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["category_id"], ["ticket_categories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignee_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["users.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("category_id", name="uq_assignment_rules_category"),
    )
    op.create_index("ix_assignment_rules_category_id", "assignment_rules", ["category_id"])
    op.create_index("ix_assignment_rules_assignee_id", "assignment_rules", ["assignee_id"])

    # --- runtime-tunable settings ------------------------------------------
    op.create_table(
        "system_settings",
        sa.Column("key", sa.String(length=64), primary_key=True),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("updated_by_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["updated_by_id"], ["users.id"], ondelete="SET NULL"),
    )


def downgrade() -> None:
    op.drop_table("system_settings")
    op.drop_index("ix_assignment_rules_assignee_id", table_name="assignment_rules")
    op.drop_index("ix_assignment_rules_category_id", table_name="assignment_rules")
    op.drop_table("assignment_rules")
    op.drop_index("ix_users_leave_window", table_name="users")
    op.drop_column("users", "leave_note")
    op.drop_column("users", "leave_to")
    op.drop_column("users", "leave_from")
