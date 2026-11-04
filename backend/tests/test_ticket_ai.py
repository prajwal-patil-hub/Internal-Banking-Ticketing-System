"""The ticket AI helpers call a model, and are honest when they cannot.

Both endpoints used to return canned text: `ai-summarize` read a column only
the email-intake path ever writes, so a portal-raised ticket always got "AI
summary not yet generated", and `ai-suggest` returned three fixed sentences.
Both still wrote an `AI_DECISION` audit row, so the trail recorded a decision
no model had made.

The tests here are about that specific failure: prove the model is actually
reached, prove the ticket's own facts are what it is given, and prove a
failure surfaces as a failure rather than as an empty success.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

import pytest

from app.services import llm_client, ticket_ai


def _ticket(**kw):
    from app.models.ticket import Ticket, TicketPriority, TicketSource, TicketStatus

    t = Ticket(
        id=uuid.uuid4(),
        ticket_number="TKT-20260827-00042",
        title="Card declined at merchant despite sufficient balance",
        description="Customer reports repeated declines on a POS terminal.",
        status=TicketStatus.IN_PROGRESS,
        priority=TicketPriority.HIGH,
        source=TicketSource.PORTAL,
        reporter_id=uuid.uuid4(),
    )
    for k, v in kw.items():
        setattr(t, k, v)
    t.created_at = t.updated_at = datetime.now(UTC)
    return t


class _Comment:
    def __init__(self, body, internal=False, author="Anita Desai", offset=0):
        self.body = body
        self.is_internal = internal
        self.author = type("A", (), {"full_name": author})()
        self.created_at = datetime.now(UTC)


# ---------------------------------------------------------------------------
# The prompt is grounded in the ticket
# ---------------------------------------------------------------------------

def test_context_carries_the_ticket_facts() -> None:
    ctx = ticket_ai.build_ticket_context(_ticket())
    assert "TKT-20260827-00042" in ctx
    assert "Card declined" in ctx
    assert "high" in ctx.lower()
    assert "POS terminal" in ctx


def test_a_breached_sla_is_stated_not_left_to_inference() -> None:
    ctx = ticket_ai.build_ticket_context(_ticket(sla_breached=True))
    assert "BREACHED" in ctx


def test_conversation_is_included_and_bounded() -> None:
    """A long thread must not spend the whole budget being re-read."""
    comments = [_Comment(f"Reply number {i}") for i in range(20)]
    ctx = ticket_ai.build_ticket_context(_ticket(), comments)
    assert "Reply number 19" in ctx
    assert "Reply number 0" not in ctx
    assert ctx.count("- Anita Desai") <= ticket_ai.MAX_COMMENTS


def test_a_long_comment_is_truncated() -> None:
    comments = [_Comment("x" * 5000)]
    ctx = ticket_ai.build_ticket_context(_ticket(), comments)
    assert len(ctx) < 5000


def test_prompts_forbid_inventing_facts() -> None:
    """The rule that matters most in a bank, pinned so it cannot be softened
    into tone guidance by a later edit."""
    for prompt in (ticket_ai.SUMMARY_PROMPT, ticket_ai.SUGGEST_PROMPT):
        assert "invent" in prompt.lower()
    assert "PII" in ticket_ai.SUMMARY_PROMPT
    assert "compliance team" in ticket_ai.SUGGEST_PROMPT


# ---------------------------------------------------------------------------
# Summarising
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_summary_reaches_the_model_and_returns_its_text(monkeypatch) -> None:
    seen = {}

    async def fake(user_message, history, *, system_prompt, max_tokens=None, temperature=None):
        seen["msg"] = user_message
        seen["sys"] = system_prompt
        return llm_client.AIResult("Customer cannot use their card at a POS terminal.", 120, 18)

    monkeypatch.setattr(llm_client, "generate", fake)
    out = await ticket_ai.summarise_ticket(_ticket())

    assert out.ok
    assert out.text == "Customer cannot use their card at a POS terminal."
    assert out.input_tokens == 120 and out.output_tokens == 18
    # Grounded: the ticket went into the prompt, not just the instructions.
    assert "TKT-20260827-00042" in seen["msg"]
    assert seen["sys"] is ticket_ai.SUMMARY_PROMPT


@pytest.mark.asyncio
async def test_summary_reports_an_unreachable_model(monkeypatch) -> None:
    async def down(*a, **k):
        return llm_client.AIResult("Cannot reach Ollama at http://x:11434", 0, 0,
                                   ok=False, error="connect")

    monkeypatch.setattr(llm_client, "generate", down)
    out = await ticket_ai.summarise_ticket(_ticket())

    assert out.ok is False
    assert "Ollama" in (out.error or "")
    assert out.text == ""


# ---------------------------------------------------------------------------
# Suggesting
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_suggestions_are_split_into_lines(monkeypatch) -> None:
    async def fake(*a, **k):
        return llm_client.AIResult(
            "Check the terminal's last settlement batch\n"
            "Confirm the card is not flagged by fraud monitoring\n"
            "Ask the branch for the exact decline code",
            200, 40,
        )

    monkeypatch.setattr(llm_client, "generate", fake)
    out = await ticket_ai.suggest_next_steps(_ticket())

    assert out.ok
    assert len(out.bullets) == 3
    assert out.bullets[0].startswith("Check the terminal")


@pytest.mark.asyncio
async def test_bullet_characters_and_numbering_are_stripped(monkeypatch) -> None:
    """Small local models add markers however firmly the prompt forbids them,
    so they are removed rather than trusted away."""
    async def fake(*a, **k):
        return llm_client.AIResult(
            "- Check the settlement batch\n"
            "2. Confirm the fraud flag\n"
            "• Ask for the decline code\n"
            "‣ Escalate to card operations",
            0, 0,
        )

    monkeypatch.setattr(llm_client, "generate", fake)
    out = await ticket_ai.suggest_next_steps(_ticket())

    assert out.bullets == [
        "Check the settlement batch",
        "Confirm the fraud flag",
        "Ask for the decline code",
        "Escalate to card operations",
    ]


@pytest.mark.asyncio
async def test_suggestions_are_capped(monkeypatch) -> None:
    async def fake(*a, **k):
        return llm_client.AIResult("\n".join(f"Action {i}" for i in range(20)), 0, 0)

    monkeypatch.setattr(llm_client, "generate", fake)
    out = await ticket_ai.suggest_next_steps(_ticket())
    assert len(out.bullets) == 5


@pytest.mark.asyncio
async def test_an_empty_reply_is_a_failure_not_an_empty_success(monkeypatch) -> None:
    """Returning [] would render as a working feature that suggests nothing —
    the same class of dishonesty as the canned text this replaced."""
    async def fake(*a, **k):
        return llm_client.AIResult("   \n\n  ", 10, 2)

    monkeypatch.setattr(llm_client, "generate", fake)
    out = await ticket_ai.suggest_next_steps(_ticket())

    assert out.ok is False
    assert out.bullets == []
    assert "no usable suggestions" in (out.error or "")


@pytest.mark.asyncio
async def test_suggestions_report_an_unreachable_model(monkeypatch) -> None:
    async def down(*a, **k):
        return llm_client.AIResult("model down", 0, 0, ok=False, error="connect")

    monkeypatch.setattr(llm_client, "generate", down)
    out = await ticket_ai.suggest_next_steps(_ticket())
    assert out.ok is False
    assert out.bullets == []


# ---------------------------------------------------------------------------
# The endpoints no longer return canned text
# ---------------------------------------------------------------------------

def test_the_canned_strings_are_gone_from_the_routes() -> None:
    """A guard against the stubs coming back.

    These exact strings were what the endpoints returned instead of calling a
    model. If either reappears, the feature has silently regressed to
    pretending.
    """
    import pathlib

    src = pathlib.Path("app/api/v1/routes/tickets.py").read_text()
    assert "AI summary not yet generated" not in src
    assert "ensure SLA targets are tracked" not in src
    assert "ai_categorization_triggered" not in src or "ai-categorize" in src
