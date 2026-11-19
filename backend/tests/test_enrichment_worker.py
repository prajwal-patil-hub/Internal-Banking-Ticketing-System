"""The intake enrichment worker.

What these pin, in order of how much they matter:

1. **It never overwrites.** Email intake writes its own category at arrival and
   a supervisor may have corrected one by hand. A later model pass must not
   silently replace either.
2. **A failed model call leaves the ticket retryable.** `categorize_ticket`
   returns a default-shaped result on failure rather than raising — writing
   that would mark the ticket enriched and it would never be retried, so the
   ticket would carry a made-up category forever.
3. **The two halves are independent.** A category failure must not cost the
   summary.
4. It fills what is missing, which is the easy part.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from unittest.mock import AsyncMock, patch

import pytest

from app.workers import enrichment_worker


@dataclass
class FakeCategorization:
    category: str = "payments"
    subcategory: str | None = "upi"
    priority: str = "high"
    confidence: float = 0.9
    risk_score: float = 0.4
    risk_factors: list | None = None
    department: str = "Payments"
    sla_recommendation: str = "4h"
    routing_reason: str = "UPI transfer failure"
    requires_escalation: bool = False
    is_regulatory: bool = False
    sentiment: str = "negative"


@dataclass
class FakeSummary:
    ok: bool = True
    text: str = "Customer reports a UPI transfer stuck for two hours."
    bullets: list | None = None
    input_tokens: int = 10
    output_tokens: int = 20
    error: str | None = None


class FakeTicket:
    """Only the attributes the worker reads or writes."""

    def __init__(self, **overrides) -> None:
        self.id = uuid.uuid4()
        self.title = "UPI transfer stuck"
        self.description = "Money debited, beneficiary not credited."
        self.email_from = None
        self.comments: list = []
        self.ai_category = None
        self.ai_subcategory = None
        self.ai_confidence = None
        self.ai_risk_score = None
        self.ai_routing_reason = None
        self.ai_sentiment = None
        self.ai_summary = None
        for k, v in overrides.items():
            setattr(self, k, v)


def _patches(categorize=None, summarise=None):
    cat = AsyncMock(return_value=categorize if categorize is not None else FakeCategorization())
    summ = AsyncMock(return_value=summarise if summarise is not None else FakeSummary())
    svc = patch("app.services.ai_service.AIService")
    return cat, summ, svc


# ---------------------------------------------------------------------------
# It never overwrites
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_does_not_overwrite_a_category_email_intake_already_wrote() -> None:
    ticket = FakeTicket(ai_category="fraud", ai_confidence=0.8, ai_summary="already here")
    cat, summ, svc = _patches()

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        changed = await enrichment_worker.enrich_ticket(object(), ticket)

    assert changed is False
    assert ticket.ai_category == "fraud"
    assert ticket.ai_confidence == 0.8
    cat.assert_not_awaited()
    summ.assert_not_awaited()


@pytest.mark.asyncio
async def test_fills_only_the_summary_when_the_category_is_already_set() -> None:
    """An email ticket has a category but never a summary."""
    ticket = FakeTicket(ai_category="fraud", ai_confidence=0.8)
    cat, summ, svc = _patches()

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        changed = await enrichment_worker.enrich_ticket(object(), ticket)

    assert changed is True
    assert ticket.ai_category == "fraud"          # untouched
    assert ticket.ai_summary                       # filled
    cat.assert_not_awaited()
    summ.assert_awaited_once()


# ---------------------------------------------------------------------------
# A failure must leave the ticket retryable
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_zero_confidence_result_is_not_written() -> None:
    """`categorize_ticket` returns a default result on failure, not an error.

    Writing that would stamp "operations / confidence 0.0" on the ticket and
    stop it ever being reconsidered — a wrong answer that looks like an answer.
    """
    failed = FakeCategorization(
        category="operations",
        confidence=0.0,
        risk_score=0.0,
        routing_reason="AI categorization failed; default routing applied.",
    )
    cat, summ, svc = _patches(categorize=failed)

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        await enrichment_worker.enrich_ticket(object(), FakeTicket())

    ticket = FakeTicket()
    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        await enrichment_worker.enrich_ticket(object(), ticket)

    assert ticket.ai_category is None
    assert ticket.ai_confidence is None


@pytest.mark.asyncio
async def test_a_raising_categoriser_does_not_cost_the_summary() -> None:
    cat = AsyncMock(side_effect=RuntimeError("ollama unreachable"))
    summ = AsyncMock(return_value=FakeSummary())
    ticket = FakeTicket()

    with patch("app.services.ai_service.AIService") as Svc, \
         patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        changed = await enrichment_worker.enrich_ticket(object(), ticket)

    assert changed is True
    assert ticket.ai_category is None     # failed, stays retryable
    assert ticket.ai_summary              # succeeded independently


@pytest.mark.asyncio
async def test_a_failed_summary_does_not_cost_the_category() -> None:
    cat, _, svc = _patches()
    summ = AsyncMock(return_value=FakeSummary(ok=False, text="", error="timeout"))
    ticket = FakeTicket()

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        changed = await enrichment_worker.enrich_ticket(object(), ticket)

    assert changed is True
    assert ticket.ai_category == "payments"
    assert ticket.ai_summary is None      # stays retryable


# ---------------------------------------------------------------------------
# The straightforward case
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_fills_an_unenriched_portal_ticket() -> None:
    """The gap this worker exists to close: a portal ticket had none of this."""
    cat, summ, svc = _patches()
    ticket = FakeTicket()

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        changed = await enrichment_worker.enrich_ticket(object(), ticket)

    assert changed is True
    assert ticket.ai_category == "payments"
    assert ticket.ai_subcategory == "upi"
    assert ticket.ai_confidence == 0.9
    assert ticket.ai_risk_score == 0.4
    assert ticket.ai_sentiment == "negative"
    assert ticket.ai_summary


@pytest.mark.asyncio
async def test_routing_reason_is_truncated_to_the_column_width() -> None:
    """`ai_routing_reason` is String(500); an over-long value would raise."""
    cat, summ, svc = _patches(categorize=FakeCategorization(routing_reason="x" * 900))
    ticket = FakeTicket()

    with svc as Svc, patch("app.services.ticket_ai.summarise_ticket", summ):
        Svc.return_value.categorize_ticket = cat
        await enrichment_worker.enrich_ticket(object(), ticket)

    assert ticket.ai_routing_reason is not None
    assert len(ticket.ai_routing_reason) == 500


# ---------------------------------------------------------------------------
# The query that selects work
# ---------------------------------------------------------------------------

def test_selects_tickets_missing_either_field() -> None:
    """Not just a missing category: email tickets have one and need a summary."""
    clause = str(enrichment_worker._needs_enrichment())
    assert "ai_category IS NULL" in clause
    assert "ai_summary IS NULL" in clause
    assert " OR " in clause
