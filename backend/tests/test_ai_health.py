"""Tests for GET /ai/health — the endpoint that explains AI failures.

The route takes no DB session, so these call it directly with stubbed
settings and a stubbed Ollama, rather than standing up the whole app.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_ollama(models: list[str] | None = None, *, error: Exception | None = None):
    """Patch httpx.AsyncClient so /api/tags returns `models` (or raises)."""
    client = AsyncMock()
    if error is not None:
        client.get.side_effect = error
    else:
        response = MagicMock()
        response.raise_for_status = MagicMock()
        response.json = MagicMock(
            return_value={"models": [{"name": n} for n in (models or [])]}
        )
        client.get.return_value = response

    ctx = MagicMock()
    ctx.__aenter__ = AsyncMock(return_value=client)
    ctx.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=ctx)


async def _health(**overrides) -> dict:
    from app.api.v1.routes import ai_chat

    defaults = {
        "AI_ENABLED": True,
        "LLM_PROVIDER": "ollama",
        "LLM_MODEL": "glm4",
        "LLM_BASE_URL": "http://host.docker.internal:11434",
        "AI_TIMEOUT_SECONDS": 180.0,
    }
    defaults.update(overrides)
    with patch.multiple(ai_chat.settings, **defaults):
        result = await ai_chat.ai_health(request=None, current_user=None)
    return result["data"]


@pytest.mark.asyncio
async def test_health_reports_model_available() -> None:
    with _stub_ollama(["glm4:latest", "llama3.1:8b"]):
        data = await _health(LLM_MODEL="glm4")

    assert data["reachable"] is True
    assert data["model_available"] is True   # bare `glm4` matches `glm4:latest`
    assert data["hint"] is None


@pytest.mark.asyncio
async def test_health_matches_exact_tag() -> None:
    with _stub_ollama(["glm4:9b", "glm4:latest"]):
        data = await _health(LLM_MODEL="glm4:latest")

    assert data["model_available"] is True


@pytest.mark.asyncio
async def test_health_flags_duplicated_env_key() -> None:
    """`LLM_MODEL=LLM_MODEL=glm4:latest` in .env must not read as a missing model.

    Regression test for a real report: the value contained the key, so the
    hint told the user to `ollama pull LLM_MODEL=glm4:latest` — sending them
    after a model problem when the actual fault was a malformed .env line.
    """
    with _stub_ollama(["glm4:9b", "glm4:latest", "llama3.1:8b"]):
        data = await _health(LLM_MODEL="LLM_MODEL=glm4:latest")

    assert data["reachable"] is True
    assert data["model_available"] is False
    hint = data["hint"]
    assert "backend/.env" in hint
    assert "LLM_MODEL=glm4:latest" in hint       # the corrected line
    assert "ollama pull LLM_MODEL=" not in hint  # never suggest pulling the junk


@pytest.mark.asyncio
async def test_health_reports_genuinely_missing_model() -> None:
    with _stub_ollama(["llama3.1:8b"]):
        data = await _health(LLM_MODEL="glm4")

    assert data["model_available"] is False
    assert "ollama pull glm4" in data["hint"]


@pytest.mark.asyncio
async def test_health_reports_unreachable_daemon() -> None:
    import httpx

    with _stub_ollama(error=httpx.ConnectError("connection refused")):
        data = await _health()

    assert data["reachable"] is False
    assert "ollama serve" in data["hint"]
    assert "OLLAMA_HOST" in data["hint"]


@pytest.mark.asyncio
async def test_health_reports_disabled_ai() -> None:
    data = await _health(AI_ENABLED=False)

    assert data["enabled"] is False
    assert "AI_ENABLED=true" in data["hint"]
