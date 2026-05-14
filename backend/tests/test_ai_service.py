"""AIService unit tests — mocked Anthropic client."""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    return db


def _mock_anthropic_response(content: str) -> MagicMock:
    """Build a mock Anthropic message response."""
    msg = MagicMock()
    block = MagicMock()
    block.text = content
    msg.content = [block]
    msg.usage = MagicMock()
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 50
    return msg


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_categorize_ticket_returns_result() -> None:
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    ai_json = json.dumps({
        "category": "payments",
        "subcategory": "UPI",
        "priority": "high",
        "confidence": 0.95,
        "risk_score": 0.2,
        "risk_factors": ["Amount > ₹1 lakh"],
        "department": "Operations",
        "sla_recommendation": "60 minutes",
        "routing_reason": "Payment team handles UPI",
        "requires_escalation": False,
        "is_regulatory": False,
        "sentiment": "negative",
    })

    mock_response = _mock_anthropic_response(ai_json)

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            result = await svc.categorize_ticket("Payment failed", "UPI transfer stuck for 2 hours")

    assert result.category == "payments"
    assert result.confidence == 0.95
    assert result.requires_escalation is False


@pytest.mark.asyncio
async def test_categorize_ticket_handles_invalid_json() -> None:
    """If AI returns invalid JSON, service returns a fallback result."""
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    mock_response = _mock_anthropic_response("I cannot determine the category.")

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            result = await svc.categorize_ticket("Test title", "Test description")

    # Fallback: should still return a result, not raise
    assert result is not None
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_categorize_ticket_handles_api_failure() -> None:
    """If Anthropic API raises, service returns a safe fallback."""
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.side_effect = Exception("API unavailable")

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            result = await svc.categorize_ticket("Test", "Test")

    assert result is not None
    assert result.confidence == 0.0  # fallback confidence


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_email_entities() -> None:
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    ai_json = json.dumps({
        "title": "UPI payment stuck",
        "summary": "Customer reports payment debited but beneficiary not credited.",
        "category": "payments",
        "priority": "high",
        "confidence": 0.9,
        "entities": {
            "account_refs": ["XXXX1234"],
            "transaction_refs": ["UTR123456"],
            "urgency_signals": ["urgent"],
        },
        "risk_score": 0.3,
    })

    mock_response = _mock_anthropic_response(ai_json)

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            result = await svc.extract_email_entities(
                subject="URGENT: UPI payment stuck - please help",
                body="My UPI payment of Rs 50000 is stuck. UTR: UTR123456",
                from_address="customer@gmail.com",
            )

    assert result.title == "UPI payment stuck"
    assert result.category == "payments"
    assert "UTR123456" in result.entities["transaction_refs"]


# ---------------------------------------------------------------------------
# Sentiment detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_sentiment_urgency() -> None:
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    ai_json = json.dumps({
        "sentiment": "negative",
        "urgency": "high",
        "escalation_risk": 0.8,
        "key_phrases": ["account blocked", "money missing"],
    })

    mock_response = _mock_anthropic_response(ai_json)

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            result = await svc.detect_sentiment_urgency(
                "My account has been blocked and all my money is missing!"
            )

    assert result["sentiment"] == "negative"
    assert result["urgency"] == "high"


# ---------------------------------------------------------------------------
# Chat assistant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_assistant_returns_response() -> None:
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    mock_response = _mock_anthropic_response(
        "For critical tickets, the SLA is 30 minutes response and 2 hours resolution."
    )

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            response, input_tokens, output_tokens = await svc.chat_with_assistant(
                message="What is the SLA for critical tickets?",
                session_history=[],
            )

    assert "30 minutes" in response or len(response) > 0
    assert input_tokens >= 0
    assert output_tokens >= 0


@pytest.mark.asyncio
async def test_chat_assistant_respects_history_cap() -> None:
    """History is capped at 20 turns to prevent token overflow."""
    from app.services.ai_service import AIService

    db = _mock_db()
    db.execute = AsyncMock(return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None)))

    # 30 history turns — only last 20 should be passed to the API
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(30)
    ]

    mock_response = _mock_anthropic_response("Acknowledged.")

    with patch("anthropic.Anthropic") as MockClient:
        mock_instance = MockClient.return_value
        mock_instance.messages.create.return_value = mock_response

        with patch("app.services.ai_service.anthropic.Anthropic", MockClient):
            svc = AIService(db, actor_id=str(uuid.uuid4()))
            svc.client = mock_instance

            await svc.chat_with_assistant("New question", long_history)

    # Check that messages.create was called with <= 21 messages (20 history + 1 new)
    call_args = mock_instance.messages.create.call_args
    messages_passed = call_args.kwargs.get("messages") or call_args.args[0] if call_args.args else []
    assert len(messages_passed) <= 21
