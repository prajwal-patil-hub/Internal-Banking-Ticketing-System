"""Align inbound_emails with the InboundEmail model.

The table was created in 0002 for a simpler intake path (a boolean
`is_processed`, a retry counter, the raw payload). The model since grew a
proper status lifecycle, spam/phishing scoring, threading and SPF/DKIM
results, but no migration ever followed — so every insert failed with
`column inbound_emails.cc_addresses does not exist` and email ingestion
could not run at all.

This brings the table to the model: adds the missing columns, drops the three
the model no longer declares, and relaxes `subject` to nullable (an email
genuinely may not have one, and rejecting it at the database is the wrong
place to notice).

`is_processed` is folded into `status` before it is dropped, so any rows
already collected keep their meaning.

Revision ID: 0006_inbound_email_columns
Revises: 0005_mfa_backup_codes
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0006_inbound_email_columns"
down_revision: Union[str, None] = "0005_mfa_backup_codes"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "inbound_emails",
        sa.Column("cc_addresses", postgresql.ARRAY(sa.String()), nullable=True),
    )
    op.add_column(
        "inbound_emails",
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
    )
    op.add_column(
        "inbound_emails",
        sa.Column("is_spam", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("inbound_emails", sa.Column("spam_score", sa.Float, nullable=True))
    op.add_column(
        "inbound_emails",
        sa.Column("is_phishing", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column(
        "inbound_emails",
        sa.Column("is_reply", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.add_column("inbound_emails", sa.Column("thread_id", sa.String(255), nullable=True))
    op.add_column(
        "inbound_emails",
        sa.Column("attachments_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column("inbound_emails", sa.Column("spf_pass", sa.Boolean, nullable=True))
    op.add_column("inbound_emails", sa.Column("dkim_pass", sa.Boolean, nullable=True))
    op.add_column("inbound_emails", sa.Column("sender_domain", sa.String(255), nullable=True))

    # Carry the old boolean forward before it disappears.
    op.execute("UPDATE inbound_emails SET status = 'processed' WHERE is_processed")

    op.alter_column("inbound_emails", "subject", existing_type=sa.String(500), nullable=True)
    op.alter_column(
        "inbound_emails",
        "processing_error",
        existing_type=sa.Text(),
        type_=sa.String(500),
        existing_nullable=True,
    )

    op.drop_index("ix_inbound_emails_processed", table_name="inbound_emails")
    op.drop_column("inbound_emails", "is_processed")
    op.drop_column("inbound_emails", "retry_count")
    op.drop_column("inbound_emails", "raw_payload")

    op.create_index("ix_inbound_emails_status", "inbound_emails", ["status"])
    op.create_index("ix_inbound_emails_thread_id", "inbound_emails", ["thread_id"])


def downgrade() -> None:
    op.drop_index("ix_inbound_emails_thread_id", table_name="inbound_emails")
    op.drop_index("ix_inbound_emails_status", table_name="inbound_emails")

    op.add_column("inbound_emails", sa.Column("raw_payload", sa.Text, nullable=True))
    op.add_column(
        "inbound_emails",
        sa.Column("retry_count", sa.Integer, nullable=False, server_default="0"),
    )
    op.add_column(
        "inbound_emails",
        sa.Column("is_processed", sa.Boolean, nullable=False, server_default=sa.false()),
    )
    op.execute("UPDATE inbound_emails SET is_processed = true WHERE status = 'processed'")
    op.create_index("ix_inbound_emails_processed", "inbound_emails", ["is_processed"])

    op.alter_column(
        "inbound_emails",
        "processing_error",
        existing_type=sa.String(500),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.execute("UPDATE inbound_emails SET subject = '' WHERE subject IS NULL")
    op.alter_column("inbound_emails", "subject", existing_type=sa.String(500), nullable=False)

    for column in (
        "sender_domain", "dkim_pass", "spf_pass", "attachments_count", "thread_id",
        "is_reply", "is_phishing", "spam_score", "is_spam", "status", "cc_addresses",
    ):
        op.drop_column("inbound_emails", column)
