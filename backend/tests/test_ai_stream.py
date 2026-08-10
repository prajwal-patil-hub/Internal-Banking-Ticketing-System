"""Tests for the SSE streaming helpers behind POST /ai/chat/stream."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _stub_stream(lines: list[str], *, error: Exception | None = None):
    """Patch httpx.AsyncClient.stream to replay `lines` as an SSE body."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()

    async def aiter_lines():
        for line in lines:
            yield line

    resp.aiter_lines = aiter_lines

    stream_ctx = MagicMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=resp)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)

    client = MagicMock()
    if error is not None:
        client.stream = MagicMock(side_effect=error)
    else:
        client.stream = MagicMock(return_value=stream_ctx)

    client_ctx = MagicMock()
    client_ctx.__aenter__ = AsyncMock(return_value=client)
    client_ctx.__aexit__ = AsyncMock(return_value=False)
    return patch("httpx.AsyncClient", return_value=client_ctx), client


def _chunk(text: str) -> str:
    return "data: " + json.dumps({"choices": [{"delta": {"content": text}}]})


async def _collect(lines: list[str]) -> list[tuple[str, object]]:
    from app.api.v1.routes.ai_chat import _stream_ollama

    patcher, _ = _stub_stream(lines)
    with patcher:
        return [item async for item in _stream_ollama("hi", [])]


# ---------------------------------------------------------------------------
# Token streaming
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_stream_yields_each_token_then_usage() -> None:
    events = await _collect([
        _chunk("Hello"),
        _chunk(" world"),
        "data: " + json.dumps({"choices": [], "usage": {"prompt_tokens": 7, "completion_tokens": 3}}),
        "data: [DONE]",
    ])

    deltas = [v for k, v in events if k == "delta"]
    assert deltas == ["Hello", " world"]
    assert events[-1] == ("usage", (7, 3))


@pytest.mark.asyncio
async def test_stream_survives_keepalives_and_malformed_frames() -> None:
    """Blank lines, comments, and bad JSON must not abort a live stream."""
    events = await _collect([
        "",
        ": keep-alive",
        _chunk("A"),
        "data: {not json",
        _chunk("B"),
        "data: [DONE]",
    ])

    assert [v for k, v in events if k == "delta"] == ["A", "B"]


@pytest.mark.asyncio
async def test_stream_tolerates_missing_usage() -> None:
    """Older Ollama builds omit the usage chunk; tokens then read as zero."""
    events = await _collect([_chunk("A"), "data: [DONE]"])

    assert events[-1] == ("usage", (0, 0))


@pytest.mark.asyncio
async def test_stream_stops_at_done_sentinel() -> None:
    events = await _collect([_chunk("A"), "data: [DONE]", _chunk("never")])

    assert [v for k, v in events if k == "delta"] == ["A"]


@pytest.mark.asyncio
async def test_stream_requests_streaming_mode() -> None:
    """The request body must actually ask Ollama to stream."""
    from app.api.v1.routes.ai_chat import _stream_ollama

    patcher, client = _stub_stream(["data: [DONE]"])
    with patcher:
        [_ async for _ in _stream_ollama("hi", [{"role": "user", "content": "prior"}])]

    body = client.stream.call_args.kwargs["json"]
    assert body["stream"] is True
    assert body["stream_options"] == {"include_usage": True}
    # system prompt + prior turn + the new message
    assert [m["role"] for m in body["messages"]] == ["system", "user", "user"]
    assert body["messages"][-1]["content"] == "hi"


@pytest.mark.asyncio
async def test_stream_propagates_connection_error() -> None:
    """Transport errors surface to the route, which turns them into an event."""
    import httpx

    from app.api.v1.routes.ai_chat import _stream_ollama

    patcher, _ = _stub_stream([], error=httpx.ConnectError("refused"))
    with patcher, pytest.raises(httpx.ConnectError):
        [_ async for _ in _stream_ollama("hi", [])]


# ---------------------------------------------------------------------------
# SSE framing
# ---------------------------------------------------------------------------

def test_sse_frame_format() -> None:
    """Frames must end in a blank line — the client splits on it."""
    from app.api.v1.routes.ai_chat import _sse

    frame = _sse("delta", {"text": "hi"})

    assert frame == 'event: delta\ndata: {"text": "hi"}\n\n'
    assert frame.endswith("\n\n")


def test_sse_escapes_newlines_in_payload() -> None:
    """A multi-line hint must not break framing — JSON escapes it to \\n."""
    from app.api.v1.routes.ai_chat import _sse

    frame = _sse("error", {"message": "line one\nline two"})

    assert frame.count("\n\n") == 1        # only the terminator
    assert "\\n" in frame                   # the payload newline is escaped
    body = frame.split("data: ", 1)[1].rstrip("\n")
    assert json.loads(body)["message"] == "line one\nline two"


# ---------------------------------------------------------------------------
# Turn ordering
# ---------------------------------------------------------------------------

def test_chat_routes_set_explicit_message_timestamps() -> None:
    """Both chat routes must stamp created_at themselves.

    Postgres now() is the transaction start time, so leaving it to the column
    default gives a user turn and its reply the identical instant. _load_history
    orders by created_at, so the tie let the model be fed its own answer before
    the question — silently corrupting multi-turn context.
    """
    import inspect

    from app.api.v1.routes import ai_chat

    for route in (ai_chat.chat, ai_chat.chat_stream):
        src = inspect.getsource(route)
        assert "created_at=asked_at" in src, f"{route.__name__} lost the user stamp"
        assert "created_at=datetime.now(UTC)" in src, (
            f"{route.__name__} lost the assistant stamp"
        )
