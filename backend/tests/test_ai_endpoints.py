"""AI endpoints — verify the wiring, error mapping, and persistence.

We don't call Anthropic from CI; we patch the AI client functions to
return predictable shapes (or raise the expected exceptions).
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_summarize_persists_summary_sentiment_risk(client, auth_headers, monkeypatch):
    from app.api.v1.routes import tickets as tickets_module  # noqa
    from app.utils import ai_client as ai_client_module
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "test-key-stub")

    async def _stub_summary(**_kwargs):
        return {"summary": "Customer cannot complete loan KYC.", "sentiment": "negative", "risk_score": 0.65}

    monkeypatch.setattr(ai_client_module, "summarize_ticket", _stub_summary)

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Loan KYC stuck", "description": "Step 3 keeps erroring", "priority": "high"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-summarize", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert body["summary"] == "Customer cannot complete loan KYC."
    assert body["sentiment"] == "negative"
    assert body["risk_score"] == 0.65

    # Re-fetch to confirm fields persisted on the ticket row.
    again = await client.get(f"/api/v1/tickets/{tid}", headers=auth_headers)
    persisted = again.json()["data"]
    assert persisted["ai_summary"] == "Customer cannot complete loan KYC."
    assert persisted["ai_sentiment"] == "negative"
    assert persisted["ai_risk_score"] == 0.65


@pytest.mark.asyncio
async def test_summarize_returns_503_when_key_missing(client, auth_headers, monkeypatch):
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "")

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Missing key", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-summarize", headers=auth_headers)
    assert r.status_code == 503, r.text
    body = r.json()
    assert body["error"]["code"] == "AI_NOT_CONFIGURED"
    assert "ANTHROPIC_API_KEY" in body["error"]["message"]


@pytest.mark.asyncio
async def test_summarize_returns_502_on_upstream_failure(client, auth_headers, monkeypatch):
    from app.utils import ai_client as ai_client_module
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "test-key-stub")

    async def _boom(**_kwargs):
        raise ai_client_module.AIServiceError("upstream 429")

    monkeypatch.setattr(ai_client_module, "summarize_ticket", _boom)

    create = await client.post(
        "/api/v1/tickets", headers=auth_headers,
        json={"title": "Upstream boom", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-summarize", headers=auth_headers)
    assert r.status_code == 502, r.text
    assert r.json()["error"]["code"] == "AI_UPSTREAM_ERROR"


@pytest.mark.asyncio
async def test_suggest_returns_real_suggestions(client, auth_headers, monkeypatch):
    from app.utils import ai_client as ai_client_module
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "test-key-stub")

    async def _stub_suggest(**_kwargs):
        return {
            "suggestions": ["Check transaction log", "Verify limits", "Escalate to compliance"],
            "next_actions": ["Email compliance lead", "Add internal note with findings"],
        }

    monkeypatch.setattr(ai_client_module, "suggest_actions", _stub_suggest)

    create = await client.post(
        "/api/v1/tickets", headers=auth_headers,
        json={"title": "Suggest test", "priority": "medium"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-suggest", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "Check transaction log" in body["suggestions"]
    assert len(body["next_actions"]) == 2


@pytest.mark.asyncio
async def test_chat_returns_user_and_assistant_messages(client, auth_headers, monkeypatch):
    """Frontend reads resp.user_message and resp.assistant_message — both must
    be present even if the AI returns an empty string."""
    from app.api.v1.routes import ai_chat as ai_chat_module
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "test-key-stub")

    async def _stub_gen(user_message, history):
        return ("Hello, I'm a stub assistant.", 12, 8)

    monkeypatch.setattr(ai_chat_module, "_generate_ai_response", _stub_gen)

    r = await client.post(
        "/api/v1/ai/chat",
        headers=auth_headers,
        json={"message": "Hi there"},
    )
    assert r.status_code == 200, r.text
    data = r.json()["data"]
    assert data["session_id"]
    assert data["user_message"]["content"] == "Hi there"
    assert data["assistant_message"]["content"] == "Hello, I'm a stub assistant."
    assert data["assistant_message"]["role"] == "assistant"
    assert data["user_message"]["role"] == "user"


@pytest.mark.asyncio
async def test_ai_client_extract_json_strips_markdown_fences(monkeypatch):
    """Defensive: models often wrap JSON in ```json fences. Extractor must cope."""
    from app.utils import ai_client as ai_client_module
    from app.core import config as _cfg

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "ANTHROPIC_API_KEY", "test-key-stub")

    async def _stub_call(prompt, max_tokens=None):
        return '```json\n{"summary": "S", "sentiment": "neutral", "risk_score": 0.2}\n```'

    monkeypatch.setattr(ai_client_module, "_call_claude", _stub_call)
    result = await ai_client_module.summarize_ticket(
        title="t", description="d", category=None, priority="low",
    )
    assert result == {"summary": "S", "sentiment": "neutral", "risk_score": 0.2}
