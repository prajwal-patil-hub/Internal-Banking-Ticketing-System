"""Pydantic schema validation tests — no DB or network required."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

_NOW = datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# Ticket schemas
# ---------------------------------------------------------------------------

def test_ticket_create_valid() -> None:
    from app.schemas.ticket import TicketCreate

    t = TicketCreate(title="Payment failed", description="UPI transfer stuck", priority="high")
    assert t.title == "Payment failed"
    assert t.priority.value == "high"


def test_ticket_create_title_required() -> None:
    from app.schemas.ticket import TicketCreate

    with pytest.raises(ValidationError):
        TicketCreate(title="", description="some description")  # type: ignore[call-arg]


def test_ticket_create_title_too_long() -> None:
    from app.schemas.ticket import TicketCreate

    with pytest.raises(ValidationError):
        TicketCreate(title="x" * 256, description="desc")  # type: ignore[call-arg]


def test_ticket_create_invalid_priority() -> None:
    from app.schemas.ticket import TicketCreate

    with pytest.raises(ValidationError):
        TicketCreate(title="Test", description="desc", priority="urgent")  # type: ignore[call-arg]


def test_ticket_update_all_optional() -> None:
    from app.schemas.ticket import TicketUpdate

    u = TicketUpdate()
    assert u.title is None
    assert u.priority is None
    assert u.assignee_id is None


def test_ticket_status_update_valid() -> None:
    from app.schemas.ticket import TicketStatusUpdate

    s = TicketStatusUpdate(status="resolved", reason="Fixed by IT team")
    assert s.status.value == "resolved"
    assert s.reason == "Fixed by IT team"


def test_ticket_status_update_reason_optional() -> None:
    from app.schemas.ticket import TicketStatusUpdate

    s = TicketStatusUpdate(status="closed")
    assert s.reason is None


def test_ticket_summary_from_dict() -> None:
    from app.schemas.ticket import TicketSummary

    data = {
        "id": str(uuid.uuid4()),
        "ticket_number": "TKT-20260513-00001",
        "title": "Card declined",
        "status": "new",
        "priority": "medium",
        "source": "email",
        "category_id": None,           # required (nullable)
        "reporter_id": str(uuid.uuid4()),
        "assignee_id": None,
        "created_at": _NOW,
        "sla_breached": False,
        "ai_confidence": None,         # required (nullable)
        "ai_risk_score": 0.2,
    }
    s = TicketSummary(**data)
    assert s.ticket_number == "TKT-20260513-00001"


def test_comment_create_valid() -> None:
    from app.schemas.ticket import CommentCreate

    c = CommentCreate(body="Customer called again", is_internal=True)
    assert c.is_internal is True


def test_comment_create_body_too_long() -> None:
    from app.schemas.ticket import CommentCreate

    with pytest.raises(ValidationError):
        CommentCreate(body="x" * 5001)


def test_comment_create_empty_body() -> None:
    from app.schemas.ticket import CommentCreate

    with pytest.raises(ValidationError):
        CommentCreate(body="")


def test_category_out_schema() -> None:
    from app.schemas.ticket import CategoryOut

    data = {
        "id": str(uuid.uuid4()),
        "code": "payments",
        "name": "Payments",
        "department": "Operations",
        "banking_domain": "payments",
        "description": "Payment-related tickets",
        "is_active": True,
        "created_at": _NOW,    # required by schema
        "updated_at": _NOW,    # required by schema
    }
    c = CategoryOut(**data)
    assert c.code == "payments"


def test_ticket_list_response() -> None:
    from app.schemas.ticket import TicketListResponse

    resp = TicketListResponse(items=[], total=0, page=1, per_page=25)
    assert resp.total == 0
    assert resp.per_page == 25


# ---------------------------------------------------------------------------
# AI schemas
# ---------------------------------------------------------------------------

def test_chat_message_in_valid() -> None:
    from app.schemas.ai import ChatMessageIn

    msg = ChatMessageIn(message="What is the SLA for critical tickets?")
    assert len(msg.message) > 0


def test_chat_message_in_empty_fails() -> None:
    from app.schemas.ai import ChatMessageIn

    with pytest.raises(ValidationError):
        ChatMessageIn(message="")


def test_chat_message_in_too_long() -> None:
    from app.schemas.ai import ChatMessageIn

    with pytest.raises(ValidationError):
        ChatMessageIn(message="x" * 4001)


def test_ai_categorization_result() -> None:
    from app.schemas.ai import AICategorizationResult

    r = AICategorizationResult(
        category="payments",
        priority="high",
        confidence=0.95,
        risk_score=0.3,
        risk_factors=["Large amount", "International transfer"],
        department="Operations",
        sla_recommendation="60 minutes",
        routing_reason="Payment team handles NEFT/RTGS issues",
        requires_escalation=False,
        is_regulatory=False,
        sentiment="negative",
    )
    assert r.confidence == 0.95
    assert r.requires_escalation is False


def test_ai_email_extraction() -> None:
    from app.schemas.ai import AIEmailExtraction

    ext = AIEmailExtraction(
        title="UPI payment stuck",
        summary="Customer reports payment debited but not credited",
        category="payments",
        priority="high",
        confidence=0.88,
        entities={
            "account_refs": ["XXXX1234"],
            "transaction_refs": ["UTR12345678"],
            "urgency_signals": ["urgent", "24 hours"],
        },
        risk_score=0.4,
    )
    assert ext.confidence == 0.88
    assert "account_refs" in ext.entities


# ---------------------------------------------------------------------------
# Dashboard schemas
# ---------------------------------------------------------------------------

def test_kpi_data_schema() -> None:
    from app.schemas.dashboard import KPIData

    kpi = KPIData(
        open_tickets=42,
        sla_breached=3,
        resolved_today=15,
        avg_resolution_hours=4.5,
        critical_open=2,
        ai_auto_categorized=38,
        email_tickets_today=10,
        escalations_active=1,
    )
    assert kpi.open_tickets == 42
    assert kpi.sla_breached == 3


def test_sla_status_schema() -> None:
    from app.schemas.dashboard import SLAStatus

    s = SLAStatus(on_time=100, at_risk=5, breached=3, compliance_rate=96.3)
    assert s.compliance_rate == 96.3


def test_audit_log_out_schema() -> None:
    from app.schemas.dashboard import AuditLogOut

    a = AuditLogOut(
        id=str(uuid.uuid4()),
        entity_type="ticket",
        entity_id=str(uuid.uuid4()),
        action="status_change",
        actor_id=str(uuid.uuid4()),
        actor_email="agent@bank.com",
        actor_role="agent",
        old_values={"status": "new"},
        new_values={"status": "assigned"},
        ip_address="10.0.0.1",
        request_id=str(uuid.uuid4()),
        created_at=_NOW,
    )
    assert a.entity_type == "ticket"
    assert a.old_values == {"status": "new"}
