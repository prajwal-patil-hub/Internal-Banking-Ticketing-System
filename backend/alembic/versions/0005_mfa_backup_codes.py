"""Single-use MFA recovery codes.

Without them a lost authenticator is a dead account: the password still works
but the second factor can never be satisfied, and only an administrator can
clear the enrolment. That is an acceptable internal answer and a poor one for
anybody else.

Codes are stored as SHA-256 hashes, never in plaintext. They are equivalent to
a password at the point of use, so a database leak must not hand over working
credentials. SHA-256 rather than Argon2 because a code carries ~50 bits of
entropy from a CSPRNG — there is no dictionary to attack, and login has to
check several hashes per attempt.

Revision ID: 0005_mfa_backup_codes
Revises: 0004_branch_operations
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_mfa_backup_codes"
down_revision: Union[str, None] = "0004_branch_operations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "mfa_backup_codes",
        sa.Column("id", sa.dialects.postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id", sa.dialects.postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False,
        ),
        sa.Column("code_hash", sa.String(length=64), nullable=False),
        # Set when spent. A used code is kept rather than deleted so the
        # security log can show that a recovery code was consumed and when.
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_mfa_backup_codes_user_id", "mfa_backup_codes", ["user_id"])
    # Lookup is by (user, hash); the unique constraint also stops the same code
    # being issued twice to one account.
    op.create_unique_constraint(
        "uq_mfa_backup_codes_user_hash", "mfa_backup_codes", ["user_id", "code_hash"]
    )


def downgrade() -> None:
    op.drop_constraint("uq_mfa_backup_codes_user_hash", "mfa_backup_codes", type_="unique")
    op.drop_index("ix_mfa_backup_codes_user_id", table_name="mfa_backup_codes")
    op.drop_table("mfa_backup_codes")
