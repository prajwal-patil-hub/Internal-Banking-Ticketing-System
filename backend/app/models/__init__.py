"""Aggregate model imports — Alembic introspects this package for metadata."""

from app.models.audit import AuditLog  # noqa: F401
from app.models.auth import LoginAttempt, RefreshToken  # noqa: F401
from app.models.branch import Branch  # noqa: F401
from app.models.category import Category  # noqa: F401
from app.models.escalation import Escalation  # noqa: F401
from app.models.notification import Notification  # noqa: F401
from app.models.role import Permission, Role, RolePermission  # noqa: F401
from app.models.sla import SLAPolicy, SLATracking  # noqa: F401
from app.models.team import Team, TeamMember  # noqa: F401
from app.models.ticket import Ticket  # noqa: F401
from app.models.ticket_history import (  # noqa: F401
    Attachment,
    TicketAssignment,
    TicketComment,
)
from app.models.user import User  # noqa: F401
