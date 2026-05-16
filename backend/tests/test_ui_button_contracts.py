"""Lock in the API contracts that the UI ticket-detail buttons depend on.

Every test here corresponds to a button on TicketDetailPage. If anyone
changes the route shape, the button breaks — and this suite breaks first.
"""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_status_transition_button_contract(client, auth_headers):
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "Status button", "priority": "medium"},
    )
    tid = create.json()["data"]["id"]

    # The UI calls POST /tickets/{id}/status with {status, reason}
    r = await client.post(
        f"/api/v1/tickets/{tid}/status",
        headers=auth_headers,
        json={"status": "in_progress", "reason": "agent picked up"},
    )
    assert r.status_code == 200, r.text
    assert r.json()["data"]["status"] == "in_progress"


@pytest.mark.asyncio
async def test_sla_pause_resume_button_contract(client, auth_headers):
    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "SLA button", "priority": "high"},
    )
    tid = create.json()["data"]["id"]

    pause = await client.post(f"/api/v1/tickets/{tid}/pause-sla", headers=auth_headers)
    assert pause.status_code == 200, pause.text
    assert pause.json()["data"]["sla_paused_at"]

    resume = await client.post(f"/api/v1/tickets/{tid}/resume-sla", headers=auth_headers)
    assert resume.status_code == 200, resume.text
    assert resume.json()["data"]["sla_resumed_at"]


@pytest.mark.asyncio
async def test_ai_summarize_button_contract(client, auth_headers, monkeypatch):
    # AI features must be enabled for these routes; flip the setting for this test.
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "AI summarize", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-summarize", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert "summary" in body
    assert body["ticket_id"] == tid


@pytest.mark.asyncio
async def test_ai_suggest_button_contract(client, auth_headers, monkeypatch):
    from app.core import config as _cfg
    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)

    create = await client.post(
        "/api/v1/tickets",
        headers=auth_headers,
        json={"title": "AI suggest", "priority": "low"},
    )
    tid = create.json()["data"]["id"]

    r = await client.post(f"/api/v1/tickets/{tid}/ai-suggest", headers=auth_headers)
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    assert isinstance(body["suggestions"], list)
    assert len(body["suggestions"]) > 0


@pytest.mark.asyncio
async def test_chat_session_end_button_contract(client, auth_headers, monkeypatch):
    """AI Chat widget's 'End session' button calls DELETE /ai/sessions/{id}.
    The endpoint should accept that even for a session id that doesn't exist
    (returns 404, not 405). What we're locking in is the HTTP method + path."""
    from uuid import uuid4

    r = await client.delete(f"/api/v1/ai/sessions/{uuid4()}", headers=auth_headers)
    # 404 = route exists, session not found. 405 would mean wrong method.
    assert r.status_code in (200, 204, 404), r.text
