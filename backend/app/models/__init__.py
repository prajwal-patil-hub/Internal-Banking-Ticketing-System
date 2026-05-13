"""Aggregate model imports — Alembic introspects this package for metadata."""

from app.models.auth import LoginAttempt, RefreshToken  # noqa: F401
from app.models.branch import Branch  # noqa: F401
from app.models.role import Permission, Role, RolePermission  # noqa: F401
from app.models.user import User  # noqa: F401
from app.models.ticket import Ticket, TicketCategory, TicketSubCategory  # noqa: F401
from app.models.comment import TicketComment  # noqa: F401
from app.models.attachment import Attachment  # noqa: F401
from app.models.sla import SLAPolicy, SLATracking  # noqa: F401
from app.models.escalation import EscalationRule, EscalationEvent  # noqa: F401
from app.models.audit import AuditLog  # noqa: F401
from app.models.email_intake import InboundEmail  # noqa: F401
from app.models.ai_interaction import ChatSession, ChatMessage, AIInteractionLog  # noqa: F401
