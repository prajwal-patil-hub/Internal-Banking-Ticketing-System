"""Model and enum validation tests — no DB required."""

from __future__ import annotations

import uuid

import pytest


# ---------------------------------------------------------------------------
# Ticket enums
# ---------------------------------------------------------------------------

def test_ticket_status_values() -> None:
    from app.models.ticket import TicketStatus

    assert TicketStatus.NEW == "new"
    assert TicketStatus.RESOLVED == "resolved"
    assert TicketStatus.CLOSED == "closed"
    assert TicketStatus.REOPENED == "reopened"
    assert len(TicketStatus) == 9


def test_ticket_priority_values() -> None:
    from app.models.ticket import TicketPriority

    assert TicketPriority.CRITICAL == "critical"
    assert TicketPriority.HIGH == "high"
    assert TicketPriority.MEDIUM == "medium"
    assert TicketPriority.LOW == "low"


def test_ticket_source_values() -> None:
    from app.models.ticket import TicketSource

    assert TicketSource.EMAIL == "email"
    assert TicketSource.PORTAL == "portal"


def test_ticket_status_string_comparison() -> None:
    """Enum values must compare equal to plain strings (API serialization)."""
    from app.models.ticket import TicketStatus

    assert TicketStatus.NEW.value == "new"
    assert str(TicketStatus.NEW) in ("new", "TicketStatus.NEW")


# ---------------------------------------------------------------------------
# Audit enums
# ---------------------------------------------------------------------------

def test_audit_action_values() -> None:
    from app.models.audit import AuditAction

    assert AuditAction.CREATE == "create"
    assert AuditAction.STATUS_CHANGE == "status_change"
    assert AuditAction.AI_DECISION == "ai_decision"
    assert len(AuditAction) == 11


# ---------------------------------------------------------------------------
# Comment enums
# ---------------------------------------------------------------------------

def test_comment_source_values() -> None:
    from app.models.comment import CommentSource

    assert CommentSource.EMAIL == "email"
    assert CommentSource.AI == "ai"
    assert CommentSource.SYSTEM == "system"


# ---------------------------------------------------------------------------
# Email intake enums
# ---------------------------------------------------------------------------

def test_email_status_values() -> None:
    from app.models.email_intake import EmailStatus

    assert EmailStatus.PENDING == "pending"
    assert EmailStatus.PROCESSED == "processed"
    assert EmailStatus.SPAM == "spam"
    assert EmailStatus.DUPLICATE == "duplicate"


# ---------------------------------------------------------------------------
# Escalation enums
# ---------------------------------------------------------------------------

def test_escalation_trigger_values() -> None:
    from app.models.escalation import EscalationTrigger

    assert EscalationTrigger.SLA_BREACH == "sla_breach"
    assert EscalationTrigger.REGULATORY == "regulatory"


# ---------------------------------------------------------------------------
# Model class attributes
# ---------------------------------------------------------------------------

def test_ticket_model_has_required_columns() -> None:
    from app.models.ticket import Ticket

    cols = {c.key for c in Ticket.__table__.columns}
    required = {
        "id", "ticket_number", "title", "description", "status", "priority",
        "source", "reporter_id", "ai_confidence", "ai_risk_score", "sla_breached",
        "email_message_id", "created_at", "updated_at",
    }
    missing = required - cols
    assert not missing, f"Ticket missing columns: {missing}"


def test_audit_log_has_no_updated_at() -> None:
    """AuditLog is append-only — no updated_at column."""
    from app.models.audit import AuditLog

    cols = {c.key for c in AuditLog.__table__.columns}
    assert "created_at" in cols
    assert "updated_at" not in cols


def test_sla_tracking_model() -> None:
    from app.models.sla import SLATracking

    cols = {c.key for c in SLATracking.__table__.columns}
    assert "ticket_id" in cols
    assert "response_due_at" in cols
    assert "resolution_due_at" in cols
    assert "is_response_breached" in cols
    assert "is_resolution_breached" in cols
    assert "total_paused_minutes" in cols


def test_inbound_email_model() -> None:
    from app.models.email_intake import InboundEmail

    cols = {c.key for c in InboundEmail.__table__.columns}
    assert "message_id" in cols
    assert "from_address" in cols
    assert "is_spam" in cols
    assert "is_phishing" in cols
    assert "thread_id" in cols


def test_chat_session_model() -> None:
    from app.models.ai_interaction import ChatSession

    cols = {c.key for c in ChatSession.__table__.columns}
    assert "user_id" in cols
    assert "title" in cols
    assert "is_active" in cols


def test_ai_interaction_log_model() -> None:
    from app.models.ai_interaction import AIInteractionLog

    cols = {c.key for c in AIInteractionLog.__table__.columns}
    assert "interaction_type" in cols
    assert "model_id" in cols
    assert "success" in cols
    assert "confidence_score" in cols
