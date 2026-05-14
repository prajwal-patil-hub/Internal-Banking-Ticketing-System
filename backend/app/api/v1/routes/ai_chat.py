"""AI chat and utility API routes.

Provides conversational AI assistance for support agents, plus standalone
utility endpoints for text categorization and email extraction.

All AI interactions are logged in ai_interaction_logs for auditability
and cost tracking.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.models.ai_interaction import AIInteractionLog, ChatMessage, ChatRole, ChatSession
from app.models.user import User
from app.schemas.envelope import ok, paginated

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
        model_id="claude-sonnet-4-6",
        prompt_tokens=input_tokens,
        completion_tokens=output_tokens,
        latency_ms=latency_ms,
        success=success,
        error_message=error_message,
        result=result,
        confidence_score=confidence_score,
    )
    db.add(entry)


def _build_system_prompt() -> str:
    return (
        "You are an AI assistant for SUCCESS Bank's internal support team. "
        "You help bank agents resolve customer tickets efficiently. "
        "Always be professional, precise, and security-conscious. "
        "Do not reveal confidential information. "
        "For regulatory and compliance questions, recommend consulting the compliance team."
    )


async def _generate_ai_response(user_message: str, history: list[dict]) -> tuple[str, int, int]:
    """Generate AI response.

    Returns (response_text, input_tokens, output_tokens).
    In production this calls the Anthropic API via the anthropic SDK.
    Returns a structured placeholder when AI is disabled or unavailable.
    """
    if not settings.AI_ENABLED:
        return (
            "AI assistance is currently disabled. Please contact your system administrator.",
            0,
            0,
        )

    try:
        import time

        import anthropic  # type: ignore[import-untyped]

        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)

        messages = []
        for turn in history:
            messages.append({"role": turn["role"], "content": turn["content"]})
        messages.append({"role": "user", "content": user_message})

        start = time.monotonic()
        response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=settings.AI_MAX_TOKENS,
            system=_build_system_prompt(),
            messages=messages,
        )
        _ = int((time.monotonic() - start) * 1000)  # latency captured for future logging

        response_text = response.content[0].text if response.content else ""
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        return response_text, input_tokens, output_tokens

    except Exception as exc:
        log.warning("ai_api_error", error=str(exc))
        return (
            "I'm sorry, I encountered an issue processing your request. Please try again shortly.",
            0,
            0,
        )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/chat", status_code=status.HTTP_200_OK, summary="Chat with AI assistant")
async def chat(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    user_message = payload.get("message", "").strip()
    if not user_message:
        raise ValidationError("message is required.")

    session_id_val = payload.get("session_id")
    ticket_id_val = payload.get("ticket_id")

    session: ChatSession | None = None

    # Resume existing session if provided
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

    # Create new session
    if session is None:
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

    # Build conversation history for AI context
    history = [
        {"role": msg.role.value, "content": msg.content}
        for msg in session.messages
        if msg.role in {ChatRole.USER, ChatRole.ASSISTANT}
    ]

    # Call AI
    import time
    start = time.monotonic()
    ai_text, input_tokens, output_tokens = await _generate_ai_response(user_message, history)
    latency_ms = int((time.monotonic() - start) * 1000)

    # Persist user message
    user_msg = ChatMessage(
        session_id=session.id,
        role=ChatRole.USER,
        content=user_message,
    )
    db.add(user_msg)

    # Persist assistant message
    assistant_msg = ChatMessage(
        session_id=session.id,
        role=ChatRole.ASSISTANT,
        content=ai_text,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
    )
    db.add(assistant_msg)

    # Log interaction
    await _log_ai_interaction(
        db,
        interaction_type="chat",
        user=current_user,
        ticket_id=session.ticket_id,
        session_id=session.id,
        result={"response_preview": ai_text[:200]},
        success=True,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )

    await db.commit()
    await db.refresh(assistant_msg)

    return ok({
        "session_id": str(session.id),
        "message": {
            "id": str(assistant_msg.id),
            "role": "assistant",
            "content": ai_text,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "created_at": assistant_msg.created_at.isoformat(),
        },
    })


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
async def get_session(
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
    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    title = payload.get("title", "").strip()
    description = payload.get("description", "").strip()

    if not title:
        raise ValidationError("title is required.")

    # Build categorization prompt
    prompt = (
        f"Analyze the following bank support ticket and provide categorization.\n\n"
        f"Title: {title}\n"
        f"Description: {description}\n\n"
        "Respond with a JSON object containing: category, subcategory, priority, sentiment, confidence (0-1), reasoning."
    )

    import time
    start = time.monotonic()
    ai_text, input_tokens, output_tokens = await _generate_ai_response(prompt, [])
    latency_ms = int((time.monotonic() - start) * 1000)

    # Parse response (best-effort JSON extraction)
    import json as json_lib
    result_data: dict = {
        "category": None,
        "subcategory": None,
        "priority": "medium",
        "sentiment": "neutral",
        "confidence": 0.0,
        "reasoning": ai_text,
    }
    try:
        # Try to extract JSON from AI response
        import re
        json_match = re.search(r"\{.*\}", ai_text, re.DOTALL)
        if json_match:
            parsed = json_lib.loads(json_match.group())
            result_data.update(parsed)
    except Exception as exc:
        log.debug("categorize_json_parse_failed", error=str(exc))

    await _log_ai_interaction(
        db,
        interaction_type="categorize",
        user=current_user,
        result=result_data,
        success=True,
        confidence_score=result_data.get("confidence"),
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        latency_ms=latency_ms,
    )
    await db.commit()

    return ok({
        "title": title,
        "description": description,
        "categorization": result_data,
    })


@router.post("/extract-email", summary="Extract ticket data from email text")
async def extract_email(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if not settings.AI_ENABLED:
        raise ValidationError("AI features are not enabled.")

    subject = payload.get("subject", "").strip()
    body = payload.get("body", "").strip()
    from_address = payload.get("from_address", "").strip()

    if not body and not subject:
        raise ValidationError("At least one of subject or body is required.")

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
    ai_text, input_tokens, output_tokens = await _generate_ai_response(prompt, [])
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
        success=True,
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
