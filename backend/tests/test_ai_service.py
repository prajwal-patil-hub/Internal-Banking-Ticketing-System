"""AIService unit tests — mocked OpenAI-compatible (Ollama) client.

AIService talks to Ollama through the `openai` SDK's chat.completions API,
so these tests stub `svc.client.chat.completions.create` and assert on the
service's parsing, fallback, and history-capping behaviour.
"""

from __future__ import annotations

import json
import uuid
from unittest.mock import AsyncMock, MagicMock

import pytest


def _mock_db() -> AsyncMock:
    db = AsyncMock()
    db.add = MagicMock()
    db.commit = AsyncMock()
    db.flush = AsyncMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    return db


def _mock_completion(content: str) -> MagicMock:
    """Build a mock OpenAI-style chat completion response."""
    response = MagicMock()
    choice = MagicMock()
    choice.message.content = content
    response.choices = [choice]
    response.usage.prompt_tokens = 100
    response.usage.completion_tokens = 50
    return response


def _service_with_reply(content: str | None = None, *, error: Exception | None = None):
    """Return (service, create_mock) with the LLM call stubbed out."""
    from app.services.ai_service import AIService

    svc = AIService(_mock_db(), actor_id=str(uuid.uuid4()))
    create = MagicMock()
    if error is not None:
        create.side_effect = error
    else:
        create.return_value = _mock_completion(content or "")
    svc.client = MagicMock()
    svc.client.chat.completions.create = create
    return svc, create


# ---------------------------------------------------------------------------
# Categorization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_categorize_ticket_returns_result() -> None:
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
    svc, _ = _service_with_reply(ai_json)

    result = await svc.categorize_ticket("Payment failed", "UPI transfer stuck for 2 hours")

    assert result.category == "payments"
    assert result.confidence == 0.95
    assert result.requires_escalation is False


@pytest.mark.asyncio
async def test_categorize_ticket_strips_markdown_fences() -> None:
    """Local models often wrap JSON in ```json fences — that must still parse."""
    payload = json.dumps({"category": "fraud", "priority": "critical", "confidence": 0.88})
    svc, _ = _service_with_reply(f"```json\n{payload}\n```")

    result = await svc.categorize_ticket("Card fraud", "Unauthorised debits overnight")

    assert result.category == "fraud"
    assert result.priority == "critical"


@pytest.mark.asyncio
async def test_categorize_ticket_handles_invalid_json() -> None:
    """If the model returns prose, the service falls back instead of raising."""
    svc, _ = _service_with_reply("I cannot determine the category.")

    result = await svc.categorize_ticket("Test title", "Test description")

    assert result is not None
    assert isinstance(result.confidence, float)
    assert 0.0 <= result.confidence <= 1.0


@pytest.mark.asyncio
async def test_categorize_ticket_handles_api_failure() -> None:
    """If Ollama is unreachable, the service returns a safe fallback."""
    svc, _ = _service_with_reply(error=Exception("Connection refused"))

    result = await svc.categorize_ticket("Test", "Test")

    assert result is not None
    assert result.confidence == 0.0  # fallback confidence
    assert result.category == "operations"


# ---------------------------------------------------------------------------
# Email extraction
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_extract_email_entities() -> None:
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
    svc, _ = _service_with_reply(ai_json)

    result = await svc.extract_email_entities(
        subject="URGENT: UPI payment stuck - please help",
        body="My UPI payment of Rs 50000 is stuck. UTR: UTR123456",
        from_address="customer@gmail.com",
    )

    assert result.title == "UPI payment stuck"
    assert result.category == "payments"
    assert "UTR123456" in result.entities["transaction_refs"]


@pytest.mark.asyncio
async def test_extract_email_entities_falls_back_to_subject() -> None:
    svc, _ = _service_with_reply(error=Exception("timeout"))

    result = await svc.extract_email_entities(
        subject="Card blocked",
        body="Please unblock my card.",
        from_address="customer@gmail.com",
    )

    assert result.title == "Card blocked"
    assert result.confidence == 0.0


# ---------------------------------------------------------------------------
# Sentiment detection
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_detect_sentiment_urgency() -> None:
    ai_json = json.dumps({
        "sentiment": "negative",
        "urgency": "high",
        "escalation_risk": 0.8,
        "key_phrases": ["account blocked", "money missing"],
    })
    svc, _ = _service_with_reply(ai_json)

    result = await svc.detect_sentiment_urgency(
        "My account has been blocked and all my money is missing!"
    )

    assert result["sentiment"] == "negative"
    assert result["urgency"] == "high"


# ---------------------------------------------------------------------------
# Summarize / draft
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summarize_ticket_returns_text() -> None:
    svc, _ = _service_with_reply("Customer's NEFT transfer failed; NPCI query raised.")

    summary = await svc.summarize_ticket({
        "id": str(uuid.uuid4()),
        "title": "NEFT failed",
        "description": "Transfer debited but not credited.",
        "status": "in_progress",
        "comments": [],
    })

    assert "NPCI" in summary


@pytest.mark.asyncio
async def test_summarize_ticket_falls_back_on_error() -> None:
    svc, _ = _service_with_reply(error=Exception("model not found"))

    summary = await svc.summarize_ticket({"id": str(uuid.uuid4()), "title": "x", "comments": []})

    assert summary == "Summary unavailable."


# ---------------------------------------------------------------------------
# Chat assistant
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_chat_assistant_returns_response() -> None:
    svc, _ = _service_with_reply(
        "For critical tickets, the SLA is 30 minutes response and 2 hours resolution."
    )

    response, input_tokens, output_tokens = await svc.chat_with_assistant(
        message="What is the SLA for critical tickets?",
        session_history=[],
    )

    assert "30 minutes" in response
    assert input_tokens == 100
    assert output_tokens == 50


@pytest.mark.asyncio
async def test_chat_assistant_falls_back_on_error() -> None:
    """A failed call must degrade to an apology, never raise into the route."""
    svc, _ = _service_with_reply(error=Exception("Connection refused"))

    response, input_tokens, output_tokens = await svc.chat_with_assistant(
        message="Anything?", session_history=[]
    )

    assert "trouble" in response.lower()
    assert (input_tokens, output_tokens) == (0, 0)


@pytest.mark.asyncio
async def test_chat_assistant_respects_history_cap() -> None:
    """History is capped at 20 turns to prevent token overflow."""
    long_history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"msg {i}"}
        for i in range(30)
    ]
    svc, create = _service_with_reply("Acknowledged.")

    await svc.chat_with_assistant("New question", long_history)

    messages = create.call_args.kwargs["messages"]
    # 1 system + 20 capped history turns + 1 new user message
    assert len(messages) == 22
    assert messages[0]["role"] == "system"
    assert messages[-1]["content"] == "New question"
    # The oldest 10 turns were dropped.
    assert all(m["content"] != "msg 0" for m in messages)


@pytest.mark.asyncio
async def test_chat_assistant_injects_context() -> None:
    svc, create = _service_with_reply("Noted.")

    await svc.chat_with_assistant(
        "What is this about?", [], context={"ticket_number": "TKT-20260101-00001"}
    )

    system_prompt = create.call_args.kwargs["messages"][0]["content"]
    assert "TKT-20260101-00001" in system_prompt
