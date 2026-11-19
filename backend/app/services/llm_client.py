"""One place that talks to the language model.

Before this module there were two independent ways to reach the model: the
`AIService` class (used only by email intake) built its own client, and
`ai_chat.py` opened raw `httpx` connections inline. Two implementations of one
job means two timeout policies, two error-message vocabularies, and two places
to change when a provider is added — and the knowledge base would have made it
three. The retrieval service uses this module instead.

`generate()` is deliberately provider-agnostic and *requires* an explicit
system prompt. The chat route's prompt is specific to chat; the knowledge
base's prompt is specific to grounded answering. A shared default would be
wrong for both, so there isn't one.

`embed()` has no Anthropic branch on purpose. Anthropic does not serve an
embeddings endpoint, and silently falling back to a different provider's
vectors would corrupt the index — vectors from two models are not comparable,
and the failure is invisible: retrieval simply returns nonsense neighbours.
Better to fail loudly at ingestion time.
"""

from __future__ import annotations

from typing import NamedTuple

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


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


class EmbeddingError(RuntimeError):
    """Embedding could not be produced.

    Raised rather than returned because there is no sensible degraded value:
    a zero vector would be indexed and retrieved as if it were real.
    """


def ollama_hint(exc: Exception) -> str:
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


def model_id() -> str:
    """Provider-qualified model name, as recorded on every log row."""
    return f"{settings.LLM_PROVIDER}:{settings.LLM_MODEL}"


async def generate(
    user_message: str,
    history: list[dict],
    *,
    system_prompt: str,
    max_tokens: int | None = None,
    temperature: float | None = None,
) -> AIResult:
    """Run one completion against the configured provider.

    Never raises for provider failures: returns `ok=False` with a
    human-readable explanation, because every caller renders the text inline
    rather than showing a stack trace.
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

            messages = [{"role": "system", "content": system_prompt}]
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
                        "temperature": (
                            settings.AI_TEMPERATURE if temperature is None else temperature
                        ),
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
            return AIResult(ollama_hint(exc), 0, 0, ok=False, error=str(exc))

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
                system=system_prompt,
                messages=messages_a,
            )
            # First block that actually carries text. Indexing [0].text assumes
            # the first block is a TextBlock, which stops being true the moment
            # a response leads with a thinking or tool-use block — and the
            # failure is an AttributeError mid-request, not a bad answer.
            response_text = next(
                (block.text for block in response.content if hasattr(block, "text")),
                "",
            )
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


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a batch of strings with the configured embedding model.

    Raises `EmbeddingError` on any failure — see the module docstring for why
    this does not degrade gracefully.

    Ollama's `/api/embed` takes a batch; older builds only expose
    `/api/embeddings` with a single `prompt`. Both are tried so the feature
    works against whatever version an operator happens to be running.
    """
    if not texts:
        return []

    if settings.LLM_PROVIDER != "ollama":
        raise EmbeddingError(
            f"Embeddings require LLM_PROVIDER=ollama; it is currently "
            f"{settings.LLM_PROVIDER!r}. The knowledge base cannot index "
            "documents without an embedding model."
        )

    import httpx

    model = settings.KB_EMBEDDING_MODEL
    base = settings.LLM_BASE_URL

    try:
        async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
            resp = await client.post(
                f"{base}/api/embed",
                json={"model": model, "input": texts, "keep_alive": settings.AI_KEEP_ALIVE},
            )
            if resp.status_code == 404:
                # Older Ollama: one text per request via /api/embeddings.
                vectors: list[list[float]] = []
                for text in texts:
                    single = await client.post(
                        f"{base}/api/embeddings",
                        json={"model": model, "prompt": text},
                    )
                    single.raise_for_status()
                    vectors.append(single.json()["embedding"])
                return _checked(vectors, model)

            resp.raise_for_status()
            payload = resp.json()
            return _checked(payload["embeddings"], model)

    except EmbeddingError:
        raise
    except Exception as exc:
        log.warning("embedding_failed", error=str(exc), model=model, url=base)
        raise EmbeddingError(
            f"Could not generate embeddings with `{model}` at {base}: {exc}. "
            f"Pull the model with `ollama pull {model}` if it is missing."
        ) from exc


def _checked(vectors: list[list[float]], model: str) -> list[list[float]]:
    """Reject vectors whose width does not match the column.

    Without this the insert fails deep inside pgvector with a message that
    names neither the model nor the setting, and the operator is left guessing
    which of the two moved.
    """
    expected = settings.KB_EMBEDDING_DIM
    for vec in vectors:
        if len(vec) != expected:
            raise EmbeddingError(
                f"Model `{model}` returned {len(vec)}-dimensional vectors but "
                f"the kb_chunks.embedding column is {expected}-wide. Either set "
                f"KB_EMBEDDING_MODEL back to a {expected}-dim model, or change "
                f"KB_EMBEDDING_DIM and run a migration that alters the column "
                f"and re-indexes every document."
            )
    return vectors
