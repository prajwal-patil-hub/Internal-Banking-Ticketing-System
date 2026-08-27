"""Central authorization policy.

One source of truth for "which roles may do what". Route modules import these
constants and guards instead of defining their own role sets — a scattered
policy is how `auditor` ended up inside the agent role set and gained write
access to tickets despite being documented as read-only.

Roles (one per user, from the `roles` table):
    admin        full control, including user and org administration
    supervisor   agent powers plus escalation queue, SLA monitor, user directory
    agent        works tickets: assign, progress, resolve, pause SLA, AI helpers
    auditor      READ ONLY — sees tickets and audit history, writes nothing
    branch_user  raises tickets, sees only their own, may close/reopen them
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from app.core.exceptions import AuthorizationError

if TYPE_CHECKING:  # pragma: no cover
    from app.models.user import User

ADMIN = "admin"
SUPERVISOR = "supervisor"
AGENT = "agent"
AUDITOR = "auditor"
BRANCH_USER = "branch_user"

#: Roles that may act on tickets — assign, transition, edit, run AI helpers.
#: `auditor` is deliberately absent: it is an oversight role, not a working one.
TICKET_WRITE_ROLES: frozenset[str] = frozenset({AGENT, SUPERVISOR, ADMIN})

#: Roles with no write access anywhere in the product.
READ_ONLY_ROLES: frozenset[str] = frozenset({AUDITOR})

#: Roles that may see the escalation queue and rules.
ESCALATION_VIEW_ROLES: frozenset[str] = frozenset({SUPERVISOR, ADMIN})

#: Roles that may read the audit trail.
AUDIT_VIEW_ROLES: frozenset[str] = frozenset({AUDITOR, ADMIN})


def role_of(user: User) -> str:
    return user.role.name


def is_read_only(user: User) -> bool:
    """True for roles that must never mutate application state.

    Super-admin does not override this: the flag widens *visibility*, and a
    read-only role holder marked super-admin is still an auditor.
    """
    return role_of(user) in READ_ONLY_ROLES


def is_branch_user(user: User) -> bool:
    return role_of(user) == BRANCH_USER


def can_write_tickets(user: User) -> bool:
    """May act on tickets belonging to other people."""
    if is_read_only(user):
        return False
    return user.is_super_admin or role_of(user) in TICKET_WRITE_ROLES


def assert_can_write(user: User, action: str = "perform this action") -> None:
    """Reject any write attempted by a read-only role."""
    if is_read_only(user):
        raise AuthorizationError(
            f"The '{role_of(user)}' role is read-only and cannot {action}."
        )


def assert_can_manage_user(actor: User, target: User) -> None:
    """Guard admin actions taken against another account.

    Being an admin is not enough to act on a *super* admin: otherwise any
    admin could reset the super admin's password, sign in as them, and hold
    every privilege in the system. Only a super admin may manage one.
    """
    if target.is_super_admin and not actor.is_super_admin:
        raise AuthorizationError(
            "Only a super admin can modify a super admin account."
        )


def assert_can_grant_super_admin(actor: User, requested: bool) -> None:
    """Only a super admin may mint another super admin.

    Without this an ordinary admin could create an account with the flag set,
    choose its password, and escalate to full control in two calls.
    """
    if requested and not actor.is_super_admin:
        raise AuthorizationError(
            "Only a super admin can grant super admin privileges."
        )


#: Roles that may create knowledge-base collections, upload documents and
#: grant access to them. Deliberately narrower than TICKET_WRITE_ROLES: an
#: agent works tickets, but publishing a document that every other agent will
#: be answered from is a curation decision, not a working one.
KB_MANAGE_ROLES: frozenset[str] = frozenset({ADMIN})

#: Roles that may ask the knowledge base a question.
#:
#: Matches the existing AI-helper guard on tickets (`agent`, `supervisor`,
#: `admin`) rather than inventing a second policy. `auditor` is excluded for
#: the same reason it cannot run the ticket AI helpers — it is an oversight
#: role, and a query spends model tokens and writes a log row. `branch_user`
#: is excluded because the knowledge base holds internal procedure; letting
#: the people who *raise* tickets query staff runbooks is a policy decision
#: for the business, not a default to slip in (open question Q2 in
#: docs/06-rag-knowledge-base.md).
KB_QUERY_ROLES: frozenset[str] = frozenset({AGENT, SUPERVISOR, ADMIN})


#: Roles the super-admin flag must never widen into knowledge-base access.
#:
#: `is_read_only` alone was not enough here. It contains only `auditor`, so a
#: `branch_user` carrying the super-admin flag fell straight through to the
#: `user.is_super_admin or ...` branch and gained both curation and query
#: rights — and, because `accessible_collections` skips the grant join for
#: super-admins, a view of every collection in the bank regardless of grants.
#: That contradicted the stated policy two lines above it. The flag is meant to
#: widen an *administrative* role's reach, not to convert a ticket-raiser into
#: one.
KB_NEVER_ROLES: frozenset[str] = frozenset({AUDITOR, BRANCH_USER})


def _kb_eligible(user: User) -> bool:
    """Gate the super-admin short-circuit itself."""
    return not is_read_only(user) and role_of(user) not in KB_NEVER_ROLES


def can_manage_knowledge_base(user: User) -> bool:
    """May curate collections and documents."""
    if not _kb_eligible(user):
        return False
    return user.is_super_admin or role_of(user) in KB_MANAGE_ROLES


def can_query_knowledge_base(user: User) -> bool:
    """May ask the knowledge base a question.

    Super-admin widens this, but never past `_kb_eligible`: an auditor or a
    branch user flagged super-admin is still an auditor or a branch user.
    """
    if not _kb_eligible(user):
        return False
    return user.is_super_admin or role_of(user) in KB_QUERY_ROLES


def assert_can_manage_knowledge_base(user: User) -> None:
    if not can_manage_knowledge_base(user):
        raise AuthorizationError(
            f"The '{role_of(user)}' role cannot manage knowledge-base content. "
            "Only administrators may upload or grant access to documents."
        )


def assert_can_query_knowledge_base(user: User) -> None:
    if not can_query_knowledge_base(user):
        raise AuthorizationError(
            f"The '{role_of(user)}' role cannot query the knowledge base."
        )
