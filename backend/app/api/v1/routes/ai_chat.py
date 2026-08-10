"""AI chat and utility API routes.

Provides conversational AI assistance for support agents, plus standalone
utility endpoints for text categorization and email extraction.

All AI interactions are logged in ai_interaction_logs for auditability
and cost tracking.
"""

from __future__ import annotations

import json
import time
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Annotated, NamedTuple

from fastapi import APIRouter, Depends, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy import Integer, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_roles
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.ratelimit import check_rate_limit
from app.db.session import SessionLocal
from app.models.ai_interaction import AIInteractionLog, ChatMessage, ChatRole, ChatSession
from app.models.user import User
from app.schemas.envelope import ok, paginated
from app.services.chat_context import build_chat_context

log = get_logger(__name__)

router = APIRouter(prefix="/ai", tags=["ai"])

# ---------------------------------------------------------------------------
# Serializers
# ---------------------------------------------------------------------------

def _serialize_session(session: ChatSession) -> dict:
    return {
        "id": str(session.id),
        "user_id": str(session.user_id),
        "ticket_id": str(session.ticket_id) if session.ticket_id else None,
        "title": session.title,
        "is_active": session.is_active,
        "ended_at": session.ended_at.isoformat() if session.ended_at else None,
        "message_count": len(session.messages),
        "created_at": session.created_at.isoformat(),
        "updated_at": session.updated_at.isoformat(),
    }


def _serialize_session_with_messages(session: ChatSession) -> dict:
    data = _serialize_session(session)
    data["messages"] = [_serialize_message(m) for m in session.messages]
    return data


def _serialize_message(message: ChatMessage) -> dict:
    return {
        "id": str(message.id),
        "session_id": str(message.session_id),
        "role": message.role.value,
        "content": message.content,
        "input_tokens": message.input_tokens,
        "output_tokens": message.output_tokens,
        "created_at": message.created_at.isoformat(),
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

async def _log_ai_interaction(
    db: AsyncSession,
    *,
    interaction_type: str,
    user: User,
    ticket_id: uuid.UUID | None = None,
    session_id: uuid.UUID | None = None,
    result: dict | None = None,
    success: bool = True,
    error_message: str | None = None,
    confidence_score: float | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int | None = None,
) -> None:
    entry = AIInteractionLog(
        user_id=user.id,
        ticket_id=ticket_id,
        session_id=session_id,
        interaction_type=interaction_type,
        model_id=f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}",
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        latency_ms=latency_ms,
        success=success,
        error_message=error_message,
        result=result,
        confidence_score=confidence_score,
    )
    db.add(entry)


def _build_system_prompt(context: str | None = None) -> str:
    """Instructions plus the grounding block for this turn.

    The rules are written as hard constraints rather than suggestions because a
    9B local model follows explicit prohibitions far more reliably than it
    follows tone guidance. The two that matter most:

    - Answer only from CONTEXT. Previously the model had no data at all and
      filled the gap with generic advice; an assistant that invents ticket
      facts in a bank is worse than one that declines.
    - Stop early. Verbosity is the dominant cost and latency driver here — the
      user waits for every token, and the reply is re-read on the next turn.
    """
    rules = [
        "You are the assistant inside SUCCESS Bank's internal ticketing system.",
        "You are talking to bank staff, not customers.",
        "",
        "HOW TO ANSWER",
        "- Answer only from the CONTEXT below and the conversation so far.",
        "- If the answer is not in CONTEXT, reply in one short sentence saying you "
        "cannot see that, and name what would help (for example: open the ticket, "
        "or ask about a ticket number). Then stop.",
        "- Never invent ticket numbers, names, amounts, dates or statuses. "
        "Quote them exactly as they appear in CONTEXT.",
        "- Never explain how to do something manually as a substitute for data "
        "you do not have. A short 'I can't see that' is the correct answer.",
        "",
        "STYLE",
        "- Be brief: at most 120 words unless the user explicitly asks for detail.",
        "- Lead with the answer. No preamble, no restating the question, no "
        "summary of what you are about to say.",
        "- Use a short bullet list only when listing several tickets or steps. "
        "Never number a list that has one item.",
        "- Do not add generic advice, disclaimers, or offers to help further.",
        "",
        "BANKING RULES",
        "- Never output full account numbers or customer PII; keep the masking "
        "used in CONTEXT.",
        "- For fraud, AML, regulatory or compliance matters, state the fact and "
        "recommend the compliance team; do not give a regulatory opinion.",
        "- You may summarise and suggest next steps. You cannot change any "
        "ticket — tell the user which button to use instead.",
    ]

    prompt = "\n".join(rules)
    if context:
        prompt += "\n\n" + context
    else:
        prompt += (
            "\n\n# CONTEXT\n(No data was available for this turn. Say you cannot "
            "see any ticket data and stop.)"
        )
    return prompt


class AIResult(NamedTuple):
    """Outcome of a single LLM call.

    `ok=False` means the text is a human-readable fallback explaining the
    failure rather than a real model completion — callers should log the
    interaction as unsuccessful but must still return 200 so the UI can
    render the explanation inline.
    """

    text: str
    input_tokens: int
    output_tokens: int
    ok: bool = True
    error: str | None = None


def _ollama_hint(exc: Exception) -> str:
    """Turn a connection failure into an actionable setup instruction."""
    import httpx

    url = settings.LLM_BASE_URL
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return (
            f"Cannot reach Ollama at {url}. Check that:\n"
            "  1. Ollama is running — `ollama serve`\n"
            "  2. It accepts connections from Docker — "
            "`launchctl setenv OLLAMA_HOST 0.0.0.0` on macOS, then restart Ollama\n"
            f"  3. The model is pulled — `ollama pull {settings.LLM_MODEL}`"
        )
    if isinstance(exc, httpx.ReadTimeout | httpx.TimeoutException):
        return (
            f"Ollama did not respond within {settings.AI_TIMEOUT_SECONDS:.0f}s. "
            f"The model `{settings.LLM_MODEL}` may still be loading — the first "
            "request after a restart is always the slowest. Please try again."
        )
    if isinstance(exc, httpx.HTTPStatusError) and exc.response.status_code == 404:
        return (
            f"Ollama does not have the model `{settings.LLM_MODEL}`. "
            f"Pull it with `ollama pull {settings.LLM_MODEL}`, then retry."
        )
    return f"Local AI (Ollama) error: {exc}"


async def _generate_ai_response(
    user_message: str,
    history: list[dict],
    *,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
) -> AIResult:
    """Generate an AI response using the configured LLM provider.

    Supports:
      - "ollama"    → local Ollama server (free, runs on Mac M2 with Metal)
      - "anthropic" → Anthropic cloud API (requires ANTHROPIC_API_KEY)
      - "none"      → disabled
    """
    if not settings.AI_ENABLED or settings.LLM_PROVIDER == "none":
        return AIResult(
            "AI assistance is currently disabled. Set LLM_PROVIDER=ollama and "
            "AI_ENABLED=true in backend/.env to enable it.",
            0,
            0,
            ok=False,
            error="ai_disabled",
        )

    # ── Ollama (local LLM, OpenAI-compatible endpoint) ──────────────────────
    if settings.LLM_PROVIDER == "ollama":
        try:
            import httpx

            messages = [{"role": "system", "content": system_prompt or _build_system_prompt()}]
            for turn in history:
                messages.append({"role": turn["role"], "content": turn["content"]})
            messages.append({"role": "user", "content": user_message})

            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                resp = await client.post(
                    f"{settings.LLM_BASE_URL}/v1/chat/completions",
                    json={
                        "model": settings.LLM_MODEL,
                        "messages": messages,
                        "max_tokens": max_tokens or settings.AI_MAX_TOKENS,
                        "temperature": settings.AI_TEMPERATURE,
                        "stream": False,
                        # Ollama-specific: keeps weights resident so the next
                        # request skips the multi-second model load.
                        "keep_alive": settings.AI_KEEP_ALIVE,
                    },
                )
                resp.raise_for_status()
                payload = resp.json()

            choice = payload["choices"][0]
            response_text: str = choice["message"]["content"]
            usage = payload.get("usage", {})
            return AIResult(
                response_text,
                usage.get("prompt_tokens", 0),
                usage.get("completion_tokens", 0),
            )

        except Exception as exc:
            log.warning(
                "ollama_api_error",
                error=str(exc),
                model=settings.LLM_MODEL,
                url=settings.LLM_BASE_URL,
            )
            return AIResult(_ollama_hint(exc), 0, 0, ok=False, error=str(exc))

    # ── Anthropic (cloud) ────────────────────────────────────────────────────
    if settings.LLM_PROVIDER == "anthropic":
        try:
            import anthropic  # type: ignore[import-untyped]

            client_a = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
            messages_a = []
            for turn in history:
                messages_a.append({"role": turn["role"], "content": turn["content"]})
            messages_a.append({"role": "user", "content": user_message})

            response = client_a.messages.create(
                model=settings.LLM_MODEL or "claude-haiku-4-5-20251001",
                max_tokens=max_tokens or settings.AI_MAX_TOKENS,
                system=system_prompt or _build_system_prompt(),
                messages=messages_a,
            )
            response_text = response.content[0].text if response.content else ""
            return AIResult(
                response_text, response.usage.input_tokens, response.usage.output_tokens
            )

        except Exception as exc:
            log.warning("anthropic_api_error", error=str(exc))
            return AIResult(
                f"The Anthropic API call failed: {exc}",
                0,
                0,
                ok=False,
                error=str(exc),
            )

    return AIResult(
        f"Unsupported LLM_PROVIDER value: {settings.LLM_PROVIDER!r}.",
        0,
        0,
        ok=False,
        error="unsupported_provider",
    )


async def _stream_ollama(
    user_message: str,
    history: list[dict],
    *,
    system_prompt: str | None = None,
    max_tokens: int | None = None,
) -> AsyncGenerator[tuple[str, object], None]:
    """Stream an Ollama completion.

    Yields ("delta", text) for each token and finally ("usage", (in, out)).
    Transport and HTTP errors propagate to the caller, which turns them into
    an SSE error event.
    """
    import httpx

    messages = [{"role": "system", "content": system_prompt or _build_system_prompt()}]
    for turn in history:
        messages.append({"role": turn["role"], "content": turn["content"]})
    messages.append({"role": "user", "content": user_message})

    body = {
        "model": settings.LLM_MODEL,
        "messages": messages,
        "max_tokens": max_tokens or settings.AI_MAX_TOKENS,
        "temperature": settings.AI_TEMPERATURE,
        "stream": True,
        # Ask for a final usage chunk; Ollama omits it on older builds, in
        # which case token counts stay at 0 rather than failing the stream.
        "stream_options": {"include_usage": True},
        "keep_alive": settings.AI_KEEP_ALIVE,
    }

    input_tokens = output_tokens = 0

    async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
        async with client.stream(
            "POST", f"{settings.LLM_BASE_URL}/v1/chat/completions", json=body
        ) as resp:
            resp.raise_for_status()
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data = line[len("data:"):].strip()
                if data == "[DONE]":
                    break
                try:
                    chunk = json.loads(data)
                except json.JSONDecodeError:
                    continue

                if usage := chunk.get("usage"):
                    input_tokens = usage.get("prompt_tokens", input_tokens)
                    output_tokens = usage.get("completion_tokens", output_tokens)

                for choice in chunk.get("choices") or []:
                    text = (choice.get("delta") or {}).get("content")
                    if text:
                        yield "delta", text

    yield "usage", (input_tokens, output_tokens)


def _sse(event: str, payload: dict) -> str:
    """Format one Server-Sent Event frame."""
    return f"event: {event}\ndata: {json.dumps(payload)}\n\n"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("/health", summary="Diagnose AI provider connectivity")
async def ai_health(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> dict:
    """Report whether the configured LLM provider is actually reachable.

    The chat endpoint deliberately never 500s on an AI failure, so this is
    the endpoint to hit when the assistant returns fallback text and you
    need to know *why*.
    """
    info: dict = {
        "enabled": settings.AI_ENABLED,
        "provider": settings.LLM_PROVIDER,
        "model": settings.LLM_MODEL,
        "base_url": settings.LLM_BASE_URL,
        "timeout_seconds": settings.AI_TIMEOUT_SECONDS,
        "reachable": False,
        "model_available": False,
        "available_models": [],
        "error": None,
        "hint": None,
    }

    if not settings.AI_ENABLED or settings.LLM_PROVIDER == "none":
        info["hint"] = "Set AI_ENABLED=true and LLM_PROVIDER=ollama in backend/.env."
        return ok(info)

    if settings.LLM_PROVIDER == "anthropic":
        info["reachable"] = bool(settings.ANTHROPIC_API_KEY)
        info["model_available"] = info["reachable"]
        if not info["reachable"]:
            info["hint"] = "ANTHROPIC_API_KEY is empty in backend/.env."
        return ok(info)

    # Ollama — ask the daemon which models it has loaded.
    try:
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(f"{settings.LLM_BASE_URL}/api/tags")
            resp.raise_for_status()
            tags = resp.json()

        names = [m.get("name", "") for m in tags.get("models", [])]
        info["reachable"] = True
        info["available_models"] = names
        # `glm4` in config should match `glm4:latest` from `ollama list`.
        wanted = settings.LLM_MODEL
        info["model_available"] = any(
            n == wanted or n.split(":")[0] == wanted.split(":")[0] for n in names
        )
        if not info["model_available"]:
            available = ", ".join(names) or "none"
            if "=" in wanted:
                # A value containing '=' is almost never a real model name; it
                # means the .env line repeated the key (LLM_MODEL=LLM_MODEL=x).
                # Telling the user to `ollama pull` that string sends them
                # chasing a model problem they don't have.
                corrected = wanted.split("=", 1)[1]
                info["hint"] = (
                    f"LLM_MODEL is set to '{wanted}', which contains an '=' and "
                    "is therefore not a valid model name. The line in "
                    f"backend/.env has most likely repeated the key — it should "
                    f"read `LLM_MODEL={corrected}`. Fix it, then recreate the "
                    "backend container so it re-reads the file: "
                    "`docker compose -f infra/docker-compose.yml up -d "
                    f"--force-recreate backend`. Available models: {available}"
                )
            else:
                info["hint"] = (
                    f"Ollama is running but `{wanted}` is not pulled. "
                    f"Run `ollama pull {wanted}`. Available: {available}"
                )
    except Exception as exc:
        info["error"] = str(exc)
        info["hint"] = _ollama_hint(exc)
        log.warning("ai_health_check_failed", error=str(exc), url=settings.LLM_BASE_URL)

    return ok(info)


async def _resolve_chat_session(
    db: AsyncSession, current_user: User, payload: dict, user_message: str
) -> tuple[ChatSession, bool]:
    """Resume the session named in the payload, or start a new one.

    Returns (session, is_new_session). Shared by the blocking and streaming
    chat routes so they cannot drift apart on validation or ownership checks.
    """
    session_id_val = payload.get("session_id")
    # Accept both ticket_id (direct) and context_id (frontend widget convention)
    ticket_id_val = payload.get("ticket_id") or payload.get("context_id")

    if session_id_val:
        try:
            session_id = uuid.UUID(str(session_id_val))
        except ValueError:
            raise ValidationError("Invalid session_id format.")

        result = await db.execute(
            select(ChatSession).where(
                ChatSession.id == session_id,
                ChatSession.user_id == current_user.id,
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise NotFoundError("Chat session not found or does not belong to you.")
        if not session.is_active:
            raise ValidationError("This chat session has ended. Start a new session.")
        return session, False

    ticket_id: uuid.UUID | None = None
    if ticket_id_val:
        try:
            ticket_id = uuid.UUID(str(ticket_id_val))
        except ValueError:
            raise ValidationError("Invalid ticket_id format.")

    session = ChatSession(
        user_id=current_user.id,
        ticket_id=ticket_id,
        title=user_message[:100],
        is_active=True,
    )
    db.add(session)
    await db.flush()
    return session, True


def _trim_history(turns: list[dict], budget: int) -> list[dict]:
    """Keep the most recent turns that fit inside a character budget.

    Counting turns is the wrong unit: twenty one-line exchanges and twenty
    pasted stack traces cost wildly different amounts, and on a local model the
    whole history is re-encoded every message. Walking backwards keeps the
    turns that matter most to the current question.
    """
    kept: list[dict] = []
    used = 0
    for turn in reversed(turns):
        cost = len(turn.get("content", "")) + 16  # rough per-message overhead
        if used + cost > budget and kept:
            break
        kept.append(turn)
        used += cost
    return list(reversed(kept))


async def _load_history(db: AsyncSession, session_id: uuid.UUID) -> list[dict]:
    """Last 20 user/assistant turns, oldest first.

    An explicit query rather than `session.messages`: the relationship's
    selectin loader only fires for query-loaded objects, so touching it on a
    freshly flushed session emits IO outside the async greenlet context and
    raises MissingGreenlet.
    """
    past = (await db.execute(
        select(ChatMessage)
        .where(
            ChatMessage.session_id == session_id,
            ChatMessage.role.in_([ChatRole.USER, ChatRole.ASSISTANT]),
        )
        .order_by(ChatMessage.created_at.desc())
        .limit(20)
    )).scalars().all()
    turns = [{"role": m.role.value, "content": m.content} for m in reversed(past)]
    return _trim_history(turns, settings.AI_HISTORY_CHAR_BUDGET)


@router.get("/usage", summary="AI token spend and latency")
async def ai_usage(
    request: Request,
    days: Annotated[int, Query(ge=1, le=90)] = 7,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(require_roles("admin", "supervisor")),
) -> dict:
    """Where the AI budget is going, broken down by interaction type.

    Token spend is otherwise invisible: every call is already logged, but
    nothing reads those rows back. Running a local model makes the marginal
    cost look like zero, which it is not — it is latency and a saturated GPU,
    and both show up here as tokens and milliseconds.
    """
    from sqlalchemy import func

    since = datetime.now(UTC) - timedelta(days=days)

    rows = (await db.execute(
        select(
            AIInteractionLog.interaction_type,
            func.count().label("calls"),
            func.sum(AIInteractionLog.prompt_tokens).label("in_tokens"),
            func.sum(AIInteractionLog.completion_tokens).label("out_tokens"),
            func.avg(AIInteractionLog.latency_ms).label("avg_latency"),
            func.max(AIInteractionLog.latency_ms).label("max_latency"),
            func.sum(func.cast(~AIInteractionLog.success, Integer)).label("failures"),
        )
        .where(AIInteractionLog.created_at >= since)
        .group_by(AIInteractionLog.interaction_type)
        .order_by(func.count().desc())
    )).all()

    by_type = [
        {
            "interaction_type": r.interaction_type,
            "calls": r.calls,
            "input_tokens": int(r.in_tokens or 0),
            "output_tokens": int(r.out_tokens or 0),
            "avg_latency_ms": round(float(r.avg_latency), 1) if r.avg_latency else None,
            "max_latency_ms": r.max_latency,
            "failures": int(r.failures or 0),
        }
        for r in rows
    ]

    top_users = (await db.execute(
        select(
            User.email,
            func.count().label("calls"),
            func.sum(
                AIInteractionLog.prompt_tokens + AIInteractionLog.completion_tokens
            ).label("tokens"),
        )
        .join(User, User.id == AIInteractionLog.user_id)
        .where(AIInteractionLog.created_at >= since)
        .group_by(User.email)
        .order_by(func.sum(
            AIInteractionLog.prompt_tokens + AIInteractionLog.completion_tokens
        ).desc())
        .limit(10)
    )).all()

    return ok({
        "window_days": days,
        "model": f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}",
        "totals": {
            "calls": sum(t["calls"] for t in by_type),
            "input_tokens": sum(t["input_tokens"] for t in by_type),
            "output_tokens": sum(t["output_tokens"] for t in by_type),
            "failures": sum(t["failures"] for t in by_type),
        },
        "by_type": by_type,
        "top_users": [
            {"email": u.email, "calls": u.calls, "tokens": int(u.tokens or 0)}
            for u in top_users
        ],
        "limits": {
            "chat_max_tokens": settings.AI_CHAT_MAX_TOKENS,
            "context_char_budget": settings.AI_CONTEXT_CHAR_BUDGET,
            "history_char_budget": settings.AI_HISTORY_CHAR_BUDGET,
            "rate_limit_per_minute": settings.AI_RATE_LIMIT_PER_MINUTE,
        },
    })


@router.post("/chat", status_code=status.HTTP_200_OK, summary="Chat with AI assistant")
async def chat(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Every path below occupies the single local model for tens of seconds.
    check_rate_limit(str(current_user.id), limit=settings.AI_RATE_LIMIT_PER_MINUTE)
    user_message = payload.get("message", "").strip()
    if not user_message:
        raise ValidationError("message is required.")

    session, is_new_session = await _resolve_chat_session(
        db, current_user, payload, user_message
    )
    # A new session has no history, so only resumed sessions need the lookup.
    history = [] if is_new_session else await _load_history(db, session.id)

    # Ground the model in real, permission-checked data. Without this the
    # assistant knows nothing about the ticket on screen and answers from
    # nowhere.
    context = await build_chat_context(
        db,
        current_user,
        ticket_id=str(session.ticket_id) if session.ticket_id else None,
        page=payload.get("page") if isinstance(payload.get("page"), dict) else None,
    )

    # Call AI
    asked_at = datetime.now(UTC)
    start = time.monotonic()
    result = await _generate_ai_response(
        user_message,
        history,
        system_prompt=_build_system_prompt(context.text),
        max_tokens=settings.AI_CHAT_MAX_TOKENS,
    )
    latency_ms = int((time.monotonic() - start) * 1000)

    # Timestamps are set explicitly, not left to the column default: Postgres
    # now() is the *transaction* start time, so both rows would land on the
    # identical instant and _load_history's ORDER BY created_at could feed the
    # model its own reply ahead of the question it answered.
    user_msg = ChatMessage(
        session_id=session.id,
        role=ChatRole.USER,
        content=user_message,
        created_at=asked_at,
    )
    db.add(user_msg)

    assistant_msg = ChatMessage(
        session_id=session.id,
        role=ChatRole.ASSISTANT,
        content=result.text,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        created_at=datetime.now(UTC),
    )
    db.add(assistant_msg)

    # Log interaction
    await _log_ai_interaction(
        db,
        interaction_type="chat",
        user=current_user,
        ticket_id=session.ticket_id,
        session_id=session.id,
        result={"response_preview": result.text[:200]},
        success=result.ok,
        error_message=result.error,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        latency_ms=latency_ms,
    )

    await db.commit()
    await db.refresh(user_msg)
    await db.refresh(assistant_msg)

    return ok({
        "session_id": str(session.id),
        "degraded": not result.ok,
        "user_message": {
            "id": str(user_msg.id),
            "session_id": str(session.id),
            "role": "user",
            "content": user_message,
            "input_tokens": None,
            "output_tokens": None,
            "created_at": user_msg.created_at.isoformat(),
        },
        "assistant_message": {
            "id": str(assistant_msg.id),
            "session_id": str(session.id),
            "role": "assistant",
            "content": result.text,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "created_at": assistant_msg.created_at.isoformat(),
        },
    })


@router.post("/chat/stream", summary="Chat with AI assistant (streamed over SSE)")
async def chat_stream(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Token-by-token variant of POST /ai/chat.

    A local model needs tens of seconds to finish a reply but produces its
    first token quickly, so streaming turns a long dead wait into immediate
    feedback.

    Events: `meta` (session id), `delta` (text fragment), `done` (message id
    and token counts), `error` (human-readable cause). Errors arrive as an
    event rather than an HTTP status because the response has already begun.
    """
    # Every path below occupies the single local model for tens of seconds.
    check_rate_limit(str(current_user.id), limit=settings.AI_RATE_LIMIT_PER_MINUTE)
    user_message = payload.get("message", "").strip()
    if not user_message:
        raise ValidationError("message is required.")

    # Everything touching `db` must happen here, before the response starts —
    # the injected session is closed as soon as this function returns, so the
    # generator below opens its own.
    session, is_new_session = await _resolve_chat_session(
        db, current_user, payload, user_message
    )
    history = [] if is_new_session else await _load_history(db, session.id)

    # Grounding is assembled here, not in the generator: it needs the request's
    # DB session, which closes the moment the response starts.
    context = await build_chat_context(
        db,
        current_user,
        ticket_id=str(session.ticket_id) if session.ticket_id else None,
        page=payload.get("page") if isinstance(payload.get("page"), dict) else None,
    )
    system_prompt = _build_system_prompt(context.text)

    session_id = session.id
    ticket_id = session.ticket_id
    user_id = current_user.id
    await db.commit()

    async def event_stream() -> AsyncGenerator[str, None]:
        # Tell the client what the assistant can actually see, so the context
        # chip reflects reality instead of implying access it may not have.
        yield _sse("meta", {
            "session_id": str(session_id),
            "context_sources": context.sources,
            "context_ticket": context.ticket_number,
            "context_denied": context.access_denied,
        })

        asked_at = datetime.now(UTC)
        start = time.monotonic()
        chunks: list[str] = []
        input_tokens = output_tokens = 0
        ok_flag = True
        error_msg: str | None = None

        if not settings.AI_ENABLED or settings.LLM_PROVIDER != "ollama":
            # Non-streaming providers (and the disabled case) still get a
            # coherent stream: one delta carrying the whole reply.
            result = await _generate_ai_response(
                user_message,
                history,
                system_prompt=system_prompt,
                max_tokens=settings.AI_CHAT_MAX_TOKENS,
            )
            chunks.append(result.text)
            input_tokens, output_tokens = result.input_tokens, result.output_tokens
            ok_flag, error_msg = result.ok, result.error
            yield _sse("delta", {"text": result.text})
        else:
            try:
                async for kind, value in _stream_ollama(
                    user_message,
                    history,
                    system_prompt=system_prompt,
                    max_tokens=settings.AI_CHAT_MAX_TOKENS,
                ):
                    if kind == "delta":
                        chunks.append(str(value))
                        yield _sse("delta", {"text": value})
                    elif kind == "usage":
                        input_tokens, output_tokens = value  # type: ignore[misc]
            except Exception as exc:
                log.warning(
                    "ollama_stream_error",
                    error=str(exc),
                    model=settings.LLM_MODEL,
                    url=settings.LLM_BASE_URL,
                )
                ok_flag = False
                error_msg = str(exc)
                hint = _ollama_hint(exc)
                # Persist the hint as the reply so the failure is visible in
                # history rather than leaving a user turn with no answer.
                if not chunks:
                    chunks.append(hint)
                    yield _sse("delta", {"text": hint})
                yield _sse("error", {"message": hint})

        full_text = "".join(chunks)
        latency_ms = int((time.monotonic() - start) * 1000)

        # Fresh session: the request-scoped one is long gone by now.
        assistant_id: uuid.UUID | None = None
        try:
            async with SessionLocal() as write_db:
                # Explicit timestamps — see the note in `chat`: the column
                # default would give both rows the transaction start time and
                # make the turn order ambiguous.
                write_db.add(ChatMessage(
                    session_id=session_id,
                    role=ChatRole.USER,
                    content=user_message,
                    created_at=asked_at,
                ))
                assistant_msg = ChatMessage(
                    session_id=session_id,
                    role=ChatRole.ASSISTANT,
                    content=full_text,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                    created_at=datetime.now(UTC),
                )
                write_db.add(assistant_msg)
                write_db.add(AIInteractionLog(
                    user_id=user_id,
                    ticket_id=ticket_id,
                    session_id=session_id,
                    interaction_type="chat_stream",
                    model_id=f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}",
                    prompt_tokens=input_tokens,
                    completion_tokens=output_tokens,
                    latency_ms=latency_ms,
                    success=ok_flag,
                    error_message=error_msg,
                    result={"response_preview": full_text[:200]},
                ))
                await write_db.commit()
                assistant_id = assistant_msg.id
        except Exception as exc:
            # The user already has the reply on screen; losing the transcript
            # write is worth a log, not a failed response.
            log.exception("chat_stream_persist_failed", error=str(exc))

        yield _sse("done", {
            "session_id": str(session_id),
            "message_id": str(assistant_id) if assistant_id else None,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "latency_ms": latency_ms,
            "degraded": not ok_flag,
        })

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            # Stops nginx from buffering the whole reply and defeating the point.
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/sessions", summary="List user's chat sessions")
async def list_sessions(
    request: Request,
    page: Annotated[int, Query(ge=1)] = 1,
    per_page: Annotated[int, Query(ge=1, le=50)] = 20,
    active_only: Annotated[bool, Query()] = False,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    from sqlalchemy import func

    stmt = select(ChatSession).where(ChatSession.user_id == current_user.id)
    if active_only:
        stmt = stmt.where(ChatSession.is_active == True)  # noqa: E712

    count_stmt = select(func.count()).select_from(stmt.subquery())
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = stmt.order_by(ChatSession.created_at.desc()).offset((page - 1) * per_page).limit(per_page)
    result = await db.execute(stmt)
    sessions = result.scalars().all()

    return paginated(
        [_serialize_session(s) for s in sessions],
        page=page,
        size=per_page,
        total=total,
    )


@router.get("/sessions/{session_id}", summary="Get session with full message history")
# NOTE: must not be named `get_session` — that would shadow the imported
# dependency of the same name for every route defined below, and FastAPI would
# silently inject this handler's return value in place of the DB session.
async def get_chat_session(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("Chat session not found.")
    return ok(_serialize_session_with_messages(session))


@router.delete("/sessions/{session_id}", summary="End chat session (soft delete)")
async def end_session(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await db.execute(
        select(ChatSession).where(
            ChatSession.id == session_id,
            ChatSession.user_id == current_user.id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("Chat session not found.")

    session.is_active = False
    session.ended_at = datetime.now(UTC)
    await db.commit()

    log.info("chat_session_ended", session_id=str(session_id), user_id=str(current_user.id))
    return ok({"session_id": str(session_id), "ended": True})


@router.post("/categorize", summary="Categorize text without creating a ticket")
async def categorize_text(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Every path below occupies the single local model for tens of seconds.
    check_rate_limit(str(current_user.id), limit=settings.AI_RATE_LIMIT_PER_MINUTE)
    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    title = payload.get("title", "").strip()
    # Accept both `text` (frontend key) and `description` (legacy key)
    description = (payload.get("text") or payload.get("description") or "").strip()

    if not title and not description:
        raise ValidationError("title or text is required.")

    # Build categorization prompt
    prompt = (
        f"Analyze the following bank support ticket and provide categorization.\n\n"
        f"Title: {title}\n"
        f"Description: {description}\n\n"
        "Respond with a JSON object containing ONLY: "
        "category (one of: payments|fraud|kyc|loans|compliance|it|operations|treasury|dispute|reconciliation|access), "
        "subcategory, priority (critical|high|medium|low), sentiment (positive|neutral|negative|urgent), "
        "confidence (0.0-1.0), department (responsible team name), tags (array of keyword strings)."
    )

    import time
    start = time.monotonic()
    result = await _generate_ai_response(prompt, [])
    ai_text, input_tokens, output_tokens = result.text, result.input_tokens, result.output_tokens
    latency_ms = int((time.monotonic() - start) * 1000)

    # Parse response (best-effort JSON extraction)
    import json as json_lib
    result_data: dict = {
        "category": "operations",
        "subcategory": None,
        "priority": "medium",
        "sentiment": "neutral",
        "confidence": 0.5,
        "department": None,
        "tags": [],
    }
    try:
        import re
        json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
        if json_match:
            parsed = json_lib.loads(json_match.group())
            result_data.update(parsed)
    except Exception as exc:
        log.debug("categorize_json_parse_failed", error=str(exc))

    # Ensure tags is always a list
    if not isinstance(result_data.get("tags"), list):
        result_data["tags"] = []

    await _log_ai_interaction(
        db,
        interaction_type="categorize",
        user=current_user,
        result=result_data,
        success=result.ok,
        error_message=result.error,
        confidence_score=result_data.get("confidence"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    await db.commit()

    # Return in CategorizeResponse format (matching frontend interface)
    return ok({
        "category":   result_data.get("category", "operations"),
        "subcategory": result_data.get("subcategory"),
        "confidence":  float(result_data.get("confidence", 0.5)),
        "priority":    result_data.get("priority", "medium"),
        "tags":        result_data.get("tags", []),
        "department":  result_data.get("department"),
    })


@router.post("/extract-email", summary="Extract ticket data from email text")
async def extract_email(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    # Every path below occupies the single local model for tens of seconds.
    check_rate_limit(str(current_user.id), limit=settings.AI_RATE_LIMIT_PER_MINUTE)
    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    subject = payload.get("subject", "").strip()
    body = payload.get("body", "").strip()
    from_address = payload.get("from_address", "").strip()

    # The frontend posts the whole message as `raw_email` — split the RFC-822
    # style headers off the body so the prompt still gets structured fields.
    raw_email = (payload.get("raw_email") or "").strip()
    if raw_email and not (subject or body):
        header_block, _, rest = raw_email.partition("\n\n")
        body = rest.strip() or raw_email
        for line in header_block.splitlines():
            key, sep, value = line.partition(":")
            if not sep:
                continue
            key_l = key.strip().lower()
            if key_l == "subject" and not subject:
                subject = value.strip()
            elif key_l == "from" and not from_address:
                from_address = value.strip()
        if not subject and not rest:
            body = raw_email

    if not body and not subject:
        raise ValidationError("At least one of subject, body, or raw_email is required.")

    prompt = (
        "Extract structured ticket data from this bank support email.\n\n"
        f"From: {from_address}\n"
        f"Subject: {subject}\n"
        f"Body:\n{body}\n\n"
        "Return JSON with: title, description, priority (critical/high/medium/low), "
        "category, customer_name, account_number (if mentioned, else null), "
        "transaction_id (if mentioned, else null), urgency_indicators, sentiment."
    )

    import time
    start = time.monotonic()
    result = await _generate_ai_response(prompt, [])
    ai_text, input_tokens, output_tokens = result.text, result.input_tokens, result.output_tokens
    latency_ms = int((time.monotonic() - start) * 1000)

    import json as json_lib
    import re

    extracted: dict = {
        "title": subject or "Support Request",
        "description": body,
        "priority": "medium",
        "category": None,
        "customer_name": None,
        "account_number": None,
        "transaction_id": None,
        "urgency_indicators": [],
        "sentiment": "neutral",
        "raw_ai_response": ai_text,
    }
    try:
        json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
        if json_match:
            parsed = json_lib.loads(json_match.group())
            extracted.update(parsed)
    except Exception as exc:
        log.debug("extract_email_json_parse_failed", error=str(exc))

    await _log_ai_interaction(
        db,
        interaction_type="extract_email",
        user=current_user,
        result=extracted,
        success=result.ok,
        error_message=result.error,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    await db.commit()

    return ok({
        "from_address": from_address,
        "subject": subject,
        "extracted": extracted,
    })
