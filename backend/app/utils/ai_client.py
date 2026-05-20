"""Thin wrapper around the Anthropic SDK with structured-JSON parsing.

Keeps the route handlers ignorant of the Claude API, and turns the three
distinct failure modes — disabled, unconfigured, upstream error — into
explicit exception classes the routes can map to clean HTTP status codes.
"""

from __future__ import annotations

import asyncio
import json
import re
from typing import Any

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)

# The model the platform is built against. Bumped here in one place.
DEFAULT_MODEL = "claude-sonnet-4-6"


class AIDisabledError(Exception):
    """Raised when AI_ENABLED=false in settings."""


class AIKeyMissingError(Exception):
    """Raised when AI is enabled but no Anthropic API key is configured."""


class AIServiceError(Exception):
    """Raised on any upstream / parsing failure."""


_SYSTEM_PROMPT = (
    "You are an analyst inside SUCCESS Bank's internal support tooling. "
    "Be precise, security-conscious, and concise. "
    "When asked to produce structured output (JSON), reply with ONLY the JSON "
    "object — no prose before or after, no markdown fences."
)


def _require_ready() -> None:
    if not settings.AI_ENABLED:
        raise AIDisabledError("AI features are disabled. Set AI_ENABLED=true to enable.")
    if not settings.ANTHROPIC_API_KEY:
        raise AIKeyMissingError(
            "AI is enabled but ANTHROPIC_API_KEY is not set. "
            "Configure the key on the backend service and restart."
        )


async def _call_claude(prompt: str, *, max_tokens: int | None = None) -> str:
    """Send one user-turn prompt to Claude and return the raw assistant text."""
    _require_ready()
    import anthropic  # type: ignore[import-untyped]

    client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

    def _sync() -> str:
        resp = client.messages.create(
            model=DEFAULT_MODEL,
            max_tokens=max_tokens or settings.AI_MAX_TOKENS,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )
        if not resp.content:
            return ""
        return resp.content[0].text or ""

    try:
        return await asyncio.to_thread(_sync)
    except Exception as exc:  # noqa: BLE001
        log.warning("ai_upstream_error", error=str(exc))
        raise AIServiceError(str(exc)) from exc


def _extract_json(raw: str) -> Any:
    """Best-effort JSON extraction.

    Models occasionally wrap JSON in markdown fences or add a sentence;
    pull out the outermost ``{...}`` block.
    """
    s = raw.strip()
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
    raw = await _call_claude(prompt, max_tokens=400)
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
    raw = await _call_claude(prompt, max_tokens=600)
    data = _extract_json(raw)
    suggestions = [str(s) for s in (data.get("suggestions") or []) if s]
    next_actions = [str(s) for s in (data.get("next_actions") or []) if s]
    if not suggestions:
        raise AIServiceError("AI returned no suggestions.")
    return {"suggestions": suggestions, "next_actions": next_actions}
