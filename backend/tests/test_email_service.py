"""EmailService unit tests — no live IMAP connection."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_db():
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.refresh = AsyncMock()
    return db


def _sample_email_data(**kwargs) -> dict:
    base = {
        "message_id": "<test-msg-001@bank.local>",
        "from_address": "customer@gmail.com",
        "to_address": "support@successbank.local",
        "subject": "Payment stuck - urgent",
        "body_text": "My UPI payment of Rs 5000 is stuck since morning. Please help.",
        "body_html": None,
        "cc_addresses": [],
        "received_at": datetime.now(timezone.utc),
        "in_reply_to": None,
        "thread_id": None,
        "attachments": [],
        "spf_pass": True,
        "dkim_pass": True,
        "sender_domain": "gmail.com",
    }
    base.update(kwargs)
    return base


# ---------------------------------------------------------------------------
# Spam scoring
# ---------------------------------------------------------------------------

def test_spam_score_clean_email_low() -> None:
    from app.services.email_service import EmailService

    db = _mock_db()
    svc = EmailService(db)

    score = svc._calculate_spam_score({
        "subject": "UPI payment failed",
        "body_text": "My payment did not go through. Please check.",
        "from_address": "customer@gmail.com",
        "spf_pass": True,
        "dkim_pass": True,
    })

    assert 0.0 <= score <= 1.0
    assert score < 0.5  # clean email should score low


def test_spam_score_suspicious_email_higher() -> None:
    from app.services.email_service import EmailService

    db = _mock_db()
    svc = EmailService(db)

    score = svc._calculate_spam_score({
        "subject": "FREE MONEY!!! Click now!!!",
        "body_text": "Win MILLION dollars NOW! Click link http://suspicious.xyz",
        "from_address": "noreply@suspicious.xyz",
        "spf_pass": False,
        "dkim_pass": False,
    })

    assert score > 0.3  # suspicious email should score higher


def test_spam_score_missing_auth_increases_score() -> None:
    from app.services.email_service import EmailService

    db = _mock_db()
    svc = EmailService(db)

    score_with_auth = svc._calculate_spam_score({
        "subject": "Account query",
        "body_text": "I have a question about my account.",
        "from_address": "user@example.com",
        "spf_pass": True,
        "dkim_pass": True,
    })

    score_without_auth = svc._calculate_spam_score({
        "subject": "Account query",
        "body_text": "I have a question about my account.",
        "from_address": "user@example.com",
        "spf_pass": False,
        "dkim_pass": False,
    })

    assert score_without_auth >= score_with_auth


# ---------------------------------------------------------------------------
# Existing ticket detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_find_existing_ticket_by_ticket_number_in_subject() -> None:
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus
    from app.services.email_service import EmailService

    db = _mock_db()
    existing = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260513-00042",
        title="Original ticket",
        description="desc",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.HIGH,
        source=TicketSource.EMAIL,
        reporter_id=uuid.uuid4(),
    )
    existing.created_at = datetime.now(timezone.utc)
    existing.updated_at = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing
    db.execute = AsyncMock(return_value=mock_result)

    svc = EmailService(db)
    found = await svc._find_existing_ticket(
        in_reply_to=None,
        subject="Re: [TKT-20260513-00042] Payment stuck",
    )

    assert found is not None
    assert found.ticket_number == "TKT-20260513-00042"


@pytest.mark.asyncio
async def test_find_existing_ticket_returns_none_for_new_email() -> None:
    from app.services.email_service import EmailService

    db = _mock_db()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    db.execute = AsyncMock(return_value=mock_result)

    svc = EmailService(db)
    found = await svc._find_existing_ticket(
        in_reply_to=None,
        subject="Brand new question about my account",
    )

    assert found is None


# ---------------------------------------------------------------------------
# Duplicate detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_duplicate_email_not_processed_twice() -> None:
    """Same Message-ID should not create a second InboundEmail record."""
    from app.models.email_intake import InboundEmail, EmailStatus
    from app.services.email_service import EmailService

    db = _mock_db()

    # Simulate existing record for this message_id
    existing_email = InboundEmail(
        id=uuid.uuid4(),
        message_id="<test-msg-001@bank.local>",
        from_address="customer@gmail.com",
        to_address="support@successbank.local",
        subject="Test",
        status=EmailStatus.PROCESSED,
        received_at=datetime.now(timezone.utc),
    )
    existing_email.created_at = datetime.now(timezone.utc)
    existing_email.updated_at = datetime.now(timezone.utc)

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = existing_email
    db.execute = AsyncMock(return_value=mock_result)

    svc = EmailService(db)
    result = await svc.process_inbound_email(_sample_email_data())

    # Should return the existing record, not create a new one
    assert result is not None
    # db.add should NOT have been called for a new record
    db.add.assert_not_called()


# ---------------------------------------------------------------------------
# New email creates ticket
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_new_email_creates_ticket() -> None:
    """A new inbound email should trigger AI extraction and ticket creation."""
    from app.services.email_service import EmailService
    from app.schemas.ai import AIEmailExtraction

    db = _mock_db()

    # No existing InboundEmail record
    call_count = 0

    async def mock_execute(stmt):
        nonlocal call_count
        call_count += 1
        m = MagicMock()
        if call_count == 1:
            # Check for duplicate message_id
            m.scalar_one_or_none.return_value = None
        elif call_count == 2:
            # Check for existing ticket (reply detection)
            m.scalar_one_or_none.return_value = None
        else:
            m.scalar_one_or_none.return_value = None
            m.scalar_one.return_value = 0
        return m

    db.execute = mock_execute

    mock_extraction = AIEmailExtraction(
        title="UPI payment stuck",
        summary="Customer's UPI payment is stuck.",
        category="payments",
        priority="high",
        confidence=0.9,
        entities={"account_refs": [], "transaction_refs": [], "urgency_signals": []},
        risk_score=0.2,
    )

    with patch("app.services.email_service.AIService") as MockAI, \
         patch("app.services.email_service.TicketService") as MockTicket:

        mock_ai = MockAI.return_value
        mock_ai.extract_email_entities = AsyncMock(return_value=mock_extraction)

        from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

        new_ticket = Ticket(
            id=uuid.uuid4(),
            ticket_number="TKT-20260513-00001",
            title="UPI payment stuck",
            description="Customer's UPI payment is stuck.",
            status=TicketStatus.NEW,
            priority=TicketPriority.HIGH,
            source=TicketSource.EMAIL,
            reporter_id=uuid.uuid4(),
        )
        new_ticket.created_at = datetime.now(timezone.utc)
        new_ticket.updated_at = datetime.now(timezone.utc)

        mock_ticket_svc = MockTicket.return_value
        mock_ticket_svc.create_ticket = AsyncMock(return_value=new_ticket)

        svc = EmailService(db)
        result = await svc.process_inbound_email(_sample_email_data())

    assert result is not None
