"""Role-Based Access Control.

Single source of truth for:
  - the set of role names (`Role`)
  - the master permission catalogue (`Permission`)
  - the role -> permissions mapping seeded into the DB

Keeping this in code means the matrix is reviewable in PRs and seeded
deterministically into every environment.
"""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    BRANCH_USER = "branch_user"
    ADMIN = "admin"
    AGENT = "agent"
    SUPERVISOR = "supervisor"
    AUDITOR = "auditor"


class Permission(StrEnum):
    # tickets
    TICKET_CREATE     = "ticket.create"
    TICKET_READ_OWN   = "ticket.read_own"
    TICKET_READ_ANY   = "ticket.read_any"
    TICKET_UPDATE     = "ticket.update"
    TICKET_ASSIGN     = "ticket.assign"
    TICKET_TRANSITION = "ticket.transition"
    TICKET_RESOLVE    = "ticket.resolve"
    TICKET_REOPEN     = "ticket.reopen"
    TICKET_CLOSE      = "ticket.close"
    TICKET_ESCALATE   = "ticket.escalate"
    TICKET_COMMENT    = "ticket.comment"
    TICKET_COMMENT_INTERNAL = "ticket.comment_internal"
    TICKET_ATTACH     = "ticket.attach"
    # admin
    USER_MANAGE       = "user.manage"
    BRANCH_MANAGE     = "branch.manage"
    TEAM_MANAGE       = "team.manage"
    CATEGORY_MANAGE   = "category.manage"
    SLA_MANAGE        = "sla.manage"
    # supervisor
    SLA_MONITOR       = "sla.monitor"
    ESCALATION_HANDLE = "escalation.handle"
    # auditor
    AUDIT_READ        = "audit.read"


# Role -> default permissions. The DB is the source of truth at runtime,
# but seeders use this map.
ROLE_PERMISSIONS: dict[Role, set[Permission]] = {
    Role.BRANCH_USER: {
        Permission.TICKET_CREATE,
        Permission.TICKET_READ_OWN,
        Permission.TICKET_COMMENT,
        Permission.TICKET_ATTACH,
        Permission.TICKET_REOPEN,
    },
    Role.AGENT: {
        Permission.TICKET_READ_ANY,
        Permission.TICKET_UPDATE,
        Permission.TICKET_TRANSITION,
        Permission.TICKET_RESOLVE,
        Permission.TICKET_COMMENT,
        Permission.TICKET_COMMENT_INTERNAL,
        Permission.TICKET_ATTACH,
        Permission.TICKET_ESCALATE,
    },
    Role.ADMIN: {
        Permission.TICKET_READ_ANY,
        Permission.TICKET_UPDATE,
        Permission.TICKET_ASSIGN,
        Permission.TICKET_TRANSITION,
        Permission.TICKET_CLOSE,
        Permission.TICKET_COMMENT,
        Permission.TICKET_COMMENT_INTERNAL,
        Permission.USER_MANAGE,
        Permission.BRANCH_MANAGE,
        Permission.TEAM_MANAGE,
        Permission.CATEGORY_MANAGE,
        Permission.SLA_MANAGE,
    },
    Role.SUPERVISOR: {
        Permission.TICKET_READ_ANY,
        Permission.TICKET_ASSIGN,
        Permission.TICKET_TRANSITION,
        Permission.TICKET_ESCALATE,
        Permission.TICKET_COMMENT,
        Permission.TICKET_COMMENT_INTERNAL,
        Permission.SLA_MONITOR,
        Permission.ESCALATION_HANDLE,
        Permission.TEAM_MANAGE,
    },
    Role.AUDITOR: {
        Permission.AUDIT_READ,
        Permission.TICKET_READ_ANY,   # read-only views
    },
}
