"""Make the audit trail immutable in the database.

The audit trail was append-only by convention: application code only ever
inserted, and nothing stopped anything else. That is not an audit trail, it is
a log that happens to be complete — and in a bank the difference is the whole
point. Anyone reaching the database with the application's own credentials
could rewrite who did what, and the record would show no sign of it.

A trigger is the right level for this rather than a `REVOKE`. Permissions are
per-role and the application connects as the owner, so a grant-based rule
would either be bypassed by the owner or would break the inserts the
application legitimately makes. A `BEFORE UPDATE OR DELETE` trigger refuses
regardless of who is connected, including the table owner and including a
superuser, and it survives a restore because it travels with the schema.

Deliberately not covered:

* **TRUNCATE** is caught by its own trigger below, because `BEFORE UPDATE OR
  DELETE` does not fire for it — an easy thing to assume and be wrong about.
* **DROP TABLE** is not, and cannot be, prevented at this level. Someone with
  rights to drop the table can also drop the trigger. What this guarantees is
  that the trail cannot be *edited* — a missing table is loud, a quietly
  altered row is not.
* **Retention deletion.** There is no retention policy yet. When one exists it
  will need a deliberate, logged path: disable the trigger inside a
  transaction, delete by age, re-enable. That should be a documented operator
  procedure, not an accident that works because nothing stopped it.

Revision ID: 0010_audit_immutability
Revises: 0009_knowledge_base
"""

from typing import Sequence, Union

from alembic import op

revision: str = "0010_audit_immutability"
down_revision: Union[str, None] = "0009_knowledge_base"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # RAISE EXCEPTION with an explicit SQLSTATE so callers can distinguish
    # "you may not do this" from a constraint violation. 42501 is
    # insufficient_privilege, which is what this is.
    op.execute(
        """
        CREATE OR REPLACE FUNCTION audit_logs_refuse_mutation()
        RETURNS TRIGGER AS $$
        BEGIN
            RAISE EXCEPTION
                'audit_logs is append-only; % is not permitted', TG_OP
                USING ERRCODE = '42501',
                      HINT = 'The audit trail is immutable by design. '
                             'Deleting by retention policy requires a '
                             'documented operator procedure.';
        END;
        $$ LANGUAGE plpgsql;
        """
    )

    op.execute(
        """
        CREATE TRIGGER audit_logs_no_update_delete
        BEFORE UPDATE OR DELETE ON audit_logs
        FOR EACH ROW EXECUTE FUNCTION audit_logs_refuse_mutation();
        """
    )

    # TRUNCATE does not fire a row-level trigger, so it needs its own. Without
    # this, the table could be emptied in one statement while the row trigger
    # sat there looking like it was protecting something.
    op.execute(
        """
        CREATE TRIGGER audit_logs_no_truncate
        BEFORE TRUNCATE ON audit_logs
        FOR EACH STATEMENT EXECUTE FUNCTION audit_logs_refuse_mutation();
        """
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_truncate ON audit_logs")
    op.execute("DROP TRIGGER IF EXISTS audit_logs_no_update_delete ON audit_logs")
    op.execute("DROP FUNCTION IF EXISTS audit_logs_refuse_mutation()")
