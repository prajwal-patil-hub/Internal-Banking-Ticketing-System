"""Let an attachment belong to a specific reply.

Files could only be attached to a ticket, which meant an agent's fix — a
corrected statement, a screenshot of the working screen — landed in the same
undifferentiated pile as the evidence the customer sent in. Nothing recorded
which answer a file belonged to.

`comment_id` is nullable: NULL keeps the existing meaning (evidence attached to
the ticket itself), a value ties the file to one reply. `ticket_id` stays
populated either way, so every file is reachable from the ticket and the
visibility rules have a single place to look.

ON DELETE CASCADE matches the ticket FK: deleting a reply takes its files with
it. The alternative — orphaning them back to the ticket — would silently expose
a file from a deleted internal note to the customer.

Revision ID: 0007_comment_attachments
Revises: 0006_inbound_email_columns
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_comment_attachments"
down_revision: Union[str, None] = "0006_inbound_email_columns"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "attachments",
        sa.Column("comment_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_attachments_comment_id",
        "attachments",
        "ticket_comments",
        ["comment_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_attachments_comment_id", "attachments", ["comment_id"])


def downgrade() -> None:
    op.drop_index("ix_attachments_comment_id", table_name="attachments")
    op.drop_constraint("fk_attachments_comment_id", "attachments", type_="foreignkey")
    op.drop_column("attachments", "comment_id")
