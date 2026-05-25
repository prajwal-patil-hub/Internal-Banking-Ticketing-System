"""Provider-agnostic LLM client.

Today we route to Groq (default, free tier) or Anthropic. Both providers
are reached through the same three functions exposed below — the route
handlers never have to care which one is configured.

Adding another OpenAI-compatible provider (OpenRouter, OpenAI, local
Ollama, vLLM, etc.) is a 4-line change: extend ``AI_PROVIDER``, set the
base URL via env, and the ``_openai_compatible_chat`` path handles the rest.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

import httpx

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


class AIDisabledError(Exception):
    """Raised when AI_ENABLED=false in settings."""


class AIKeyMissingError(Exception):
    """Raised when the selected provider's API key is empty."""


class AIServiceError(Exception):
    """Raised on any upstream / parsing failure."""


_SYSTEM_PROMPT = (
    "You are an analyst inside SUCCESS Bank's internal support tooling. "
    "Be precise, security-conscious, and concise. "
    "When asked to produce structured output (JSON), reply with ONLY the JSON "
    "object — no prose before or after, no markdown fences."
)


# ---------------------------------------------------------------------------
# Provider routing
# ---------------------------------------------------------------------------

def _require_ready() -> None:
    if not settings.AI_ENABLED:
        raise AIDisabledError("AI features are disabled. Set AI_ENABLED=true to enable.")
    if not settings.ai_provider_key:
        raise AIKeyMissingError(
            f"AI is enabled but {settings.ai_provider_key_env_name} is not set. "
            f"Configure the key on the backend service and restart."
        )


async def call_llm(
    *,
    user_message: str,
    history: list[dict] | None = None,
    max_tokens: int | None = None,
    json_mode: bool = False,
) -> tuple[str, int, int]:
    """Send one prompt to the configured provider. Returns (text, in_tokens, out_tokens)."""
    _require_ready()
    history = history or []

    if settings.AI_PROVIDER == "groq":
        return await _openai_compatible_chat(
            base_url=settings.GROQ_BASE_URL,
            api_key=settings.GROQ_API_KEY,
            model=settings.GROQ_MODEL,
            user_message=user_message,
            history=history,
            max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            json_mode=json_mode,
        )
    return await _anthropic_chat(
        user_message=user_message,
        history=history,
        max_tokens=max_tokens or settings.AI_MAX_TOKENS,
    )


# Kept for backwards-compat with tests that monkeypatched the old helper.
async def _call_claude(prompt: str, *, max_tokens: int | None = None) -> str:
    text, _, _ = await call_llm(user_message=prompt, max_tokens=max_tokens, json_mode=True)
    return text


# ---------------------------------------------------------------------------
# Groq / any OpenAI-compatible provider
# ---------------------------------------------------------------------------

async def _openai_compatible_chat(
    *,
    base_url: str,
    api_key: str,
    model: str,
    user_message: str,
    history: list[dict],
    max_tokens: int,
    json_mode: bool,
) -> tuple[str, int, int]:
    messages: list[dict[str, Any]] = [{"role": "system", "content": _SYSTEM_PROMPT}]
    for turn in history:
        if turn.get("role") in {"user", "assistant"}:
            messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": 0.2,
    }
    if json_mode:
        # Groq supports OpenAI's response_format on llama-3.3 and newer.
        payload["response_format"] = {"type": "json_object"}

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            r = await client.post(
                f"{base_url.rstrip('/')}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.HTTPError as exc:
        log.warning("ai_network_error", provider=settings.AI_PROVIDER, error=str(exc))
        raise AIServiceError(f"Network error contacting {settings.AI_PROVIDER}: {exc}") from exc

    if r.status_code >= 400:
        log.warning(
            "ai_upstream_error",
            provider=settings.AI_PROVIDER,
            status=r.status_code,
            body=r.text[:500],
        )
        raise AIServiceError(
            f"{settings.AI_PROVIDER} returned HTTP {r.status_code}: {r.text[:200]}"
        )

    try:
        data = r.json()
        text: str = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage") or {}
        return text, int(usage.get("prompt_tokens") or 0), int(usage.get("completion_tokens") or 0)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        log.warning("ai_response_parse_error", provider=settings.AI_PROVIDER, error=str(exc))
        raise AIServiceError("Could not parse provider response.") from exc


# ---------------------------------------------------------------------------
# Anthropic
# ---------------------------------------------------------------------------

async def _anthropic_chat(
    *,
    user_message: str,
    history: list[dict],
    max_tokens: int,
) -> tuple[str, int, int]:
    import anthropic  # type: ignore[import-untyped]

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    messages = [
        {"role": t["role"], "content": t["content"]}
        for t in history
        if t.get("role") in {"user", "assistant"}
    ]
    messages.append({"role": "user", "content": user_message})

    def _sync() -> Any:
        return client.messages.create(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=max_tokens,
            system=_SYSTEM_PROMPT,
            messages=messages,
        )

    try:
        resp = await asyncio.to_thread(_sync)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_upstream_error", provider="anthropic", error=str(exc))
        raise AIServiceError(str(exc)) from exc

    text = resp.content[0].text if resp.content else ""
    return text, int(resp.usage.input_tokens), int(resp.usage.output_tokens)


# ---------------------------------------------------------------------------
# JSON extraction and high-level helpers
# ---------------------------------------------------------------------------

def _extract_json(raw: str) -> Any:
    s = (raw or "").strip()
    if s.startswith("```"):
        s = re.sub(r"^```(?:json)?\s*", "", s)
        s = re.sub(r"\s*```$", "", s)
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", s, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                pass
        raise AIServiceError("AI returned non-JSON output.")


def _coerce_float(v: Any, default: float = 0.0) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return default
    if f != f:  # NaN
        return default
    return max(0.0, min(1.0, f))


async def summarize_ticket(
    *, title: str, description: str, category: str | None, priority: str
) -> dict:
    """Return ``{summary, sentiment, risk_score}`` for a ticket."""
    prompt = (
        "Summarise the following internal banking ticket in 2-3 sentences. "
        "Also return a sentiment label and a fraud/operational risk score in [0,1]. "
        "Respond as JSON exactly:\n"
        '{"summary": "...", "sentiment": "positive|neutral|negative", "risk_score": 0.0}\n\n'
        f"Title: {title}\n"
        f"Priority: {priority}\n"
        f"Category: {category or 'unknown'}\n"
        f"Description: {description or '(none provided)'}\n"
    )
    raw, _, _ = await call_llm(user_message=prompt, max_tokens=400, json_mode=True)
    data = _extract_json(raw)
    sentiment = str(data.get("sentiment") or "neutral").lower()
    if sentiment not in {"positive", "neutral", "negative"}:
        sentiment = "neutral"
    return {
        "summary": str(data.get("summary") or "").strip()
        or "(model returned an empty summary)",
        "sentiment": sentiment,
        "risk_score": _coerce_float(data.get("risk_score")),
    }


async def suggest_actions(
    *, title: str, description: str, category: str | None, priority: str
) -> dict:
    """Return ``{suggestions: [str], next_actions: [str]}``."""
    prompt = (
        "Given the ticket below, suggest 3-5 concrete resolution steps and 2-3 "
        "next actions an agent should take. Respond as JSON exactly:\n"
        '{"suggestions": ["...", "..."], "next_actions": ["...", "..."]}\n\n'
        f"Title: {title}\n"
        f"Priority: {priority}\n"
        f"Category: {category or 'unknown'}\n"
        f"Description: {description or '(none provided)'}\n"
    )
    raw, _, _ = await call_llm(user_message=prompt, max_tokens=600, json_mode=True)
    data = _extract_json(raw)
    suggestions = [str(s) for s in (data.get("suggestions") or []) if s]
    next_actions = [str(s) for s in (data.get("next_actions") or []) if s]
    if not suggestions:
        raise AIServiceError("AI returned no suggestions.")
    return {"suggestions": suggestions, "next_actions": next_actions}
