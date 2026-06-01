"""PII redactor — pattern coverage + black-box check that call_llm
actually scrubs prompts before sending."""

from __future__ import annotations

import pytest

from app.utils.pii import redact_message_list, redact_pii


# ---------------------------------------------------------------------------
# Pattern coverage
# ---------------------------------------------------------------------------

class TestRedactionPatterns:
    def test_pan_is_redacted(self):
        r = redact_pii("PAN on file is ABCDE1234F please verify.")
        assert "ABCDE1234F" not in r.text
        assert "[REDACTED_PAN]" in r.text
        assert r.counts == {"pan": 1}

    def test_aadhaar_with_and_without_spaces(self):
        # Both grouped and ungrouped forms.
        for raw in ("1234 5678 9012", "123456789012", "1234-5678-9012"):
            r = redact_pii(f"Customer aadhaar: {raw}")
            assert raw not in r.text
            assert "[REDACTED_AADHAAR]" in r.text

    def test_credit_card_redacted_before_account_fallback(self):
        r = redact_pii("Card 4111 1111 1111 1111 was declined.")
        assert "4111" not in r.text
        assert "[REDACTED_CARD]" in r.text
        # And not split into pieces that the account regex would also match.
        assert "[REDACTED_ACCOUNT]" not in r.text

    def test_ifsc_redacted(self):
        r = redact_pii("Beneficiary IFSC SBIN0001234 needs verification.")
        assert "SBIN0001234" not in r.text
        assert "[REDACTED_IFSC]" in r.text

    def test_email_redacted_before_upi(self):
        r = redact_pii("Reply to customer@bank.com or 9876543210@ybl.")
        assert "customer@bank.com" not in r.text
        assert "[REDACTED_EMAIL]" in r.text
        # The UPI handle (no TLD) should still be caught by the UPI pattern.
        assert "9876543210@ybl" not in r.text
        assert "[REDACTED_UPI]" in r.text

    def test_indian_phone_number_redacted(self):
        for raw in ("9876543210", "+91 9876543210", "+91-98765-43210", "098765 43210"):
            r = redact_pii(f"Call {raw} for confirmation.")
            assert "98765" not in r.text, f"failed to redact {raw!r}"
            assert "[REDACTED_PHONE]" in r.text

    def test_long_account_number_redacted_as_fallback(self):
        r = redact_pii("Account 50100123456789 pending KYC.")
        assert "50100123456789" not in r.text
        assert "[REDACTED_ACCOUNT]" in r.text

    def test_cvv_in_context_is_redacted(self):
        r = redact_pii("Customer shared CVV: 123 by mistake.")
        assert "[REDACTED_CVV]" in r.text

    def test_short_bare_number_is_not_treated_as_pii(self):
        """3-digit standalone integers (counts, order numbers) must not be
        eaten by the CVV rule — that rule needs explicit 'cvv' context."""
        r = redact_pii("Resolved 123 tickets this week, 9 escalations.")
        assert r.counts == {}
        assert "123" in r.text and "9" in r.text

    def test_url_with_query_string_does_not_match_account_pattern(self):
        r = redact_pii("See https://example.com/ticket?ref=12345 thanks.")
        # 5-digit refs are below the 10-digit floor; nothing should fire.
        assert r.counts == {}

    def test_redaction_is_idempotent(self):
        once = redact_pii("Aadhaar 1234 5678 9012 and PAN ABCDE1234F.")
        twice = redact_pii(once.text)
        assert once.text == twice.text
        assert twice.counts == {}

    def test_none_and_empty_input_safe(self):
        assert redact_pii("").counts == {}
        assert redact_pii(None).text == ""  # type: ignore[arg-type]

    def test_message_list_redacts_each_turn_and_aggregates_counts(self):
        msgs = [
            {"role": "user", "content": "My PAN is ABCDE1234F"},
            {"role": "assistant", "content": "Got it."},
            {"role": "user", "content": "Email me at jane@example.com"},
        ]
        out, counts = redact_message_list(msgs)
        assert out[0]["content"] != msgs[0]["content"]
        assert "ABCDE1234F" not in out[0]["content"]
        assert "jane@example.com" not in out[2]["content"]
        assert counts == {"pan": 1, "email": 1}


# ---------------------------------------------------------------------------
# Black-box: prompts leaving call_llm must be scrubbed
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_call_llm_scrubs_user_message_before_sending(monkeypatch):
    """Stub the HTTP transport and assert no raw PII reaches it."""
    from app.core import config as _cfg
    from app.utils import ai_client as ai

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(_cfg.settings, "GROQ_API_KEY", "gsk_stub")

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", _Client)

    raw = (
        "Customer ABCDE1234F (Aadhaar 1234 5678 9012) called from "
        "+91 9876543210, card 4111 1111 1111 1111, email jane@example.com, "
        "IFSC SBIN0001234, UPI 9876543210@ybl."
    )
    await ai.call_llm(user_message=raw, history=[{"role": "user", "content": "PAN ABCDE1234F"}])

    sent_messages = captured["json"]["messages"]
    sent_blob = " ".join(m["content"] for m in sent_messages if isinstance(m.get("content"), str))

    # Every secret must be gone.
    for secret in (
        "ABCDE1234F", "1234 5678 9012", "9876543210", "4111 1111 1111 1111",
        "jane@example.com", "SBIN0001234", "9876543210@ybl",
    ):
        assert secret not in sent_blob, f"PII leaked to provider: {secret!r}"

    # Markers should be present so the model still sees structure.
    assert "[REDACTED_PAN]" in sent_blob
    assert "[REDACTED_AADHAAR]" in sent_blob
    assert "[REDACTED_PHONE]" in sent_blob
    assert "[REDACTED_CARD]" in sent_blob
    assert "[REDACTED_EMAIL]" in sent_blob
    assert "[REDACTED_IFSC]" in sent_blob
    assert "[REDACTED_UPI]" in sent_blob


@pytest.mark.asyncio
async def test_call_llm_opt_out_when_redact_pii_false(monkeypatch):
    """A caller that has already redacted (or has explicit clearance) can pass
    redact_pii=False; the prompt must reach the provider untouched."""
    from app.core import config as _cfg
    from app.utils import ai_client as ai

    monkeypatch.setattr(_cfg.settings, "AI_ENABLED", True)
    monkeypatch.setattr(_cfg.settings, "AI_PROVIDER", "groq")
    monkeypatch.setattr(_cfg.settings, "GROQ_API_KEY", "gsk_stub")

    captured: dict = {}

    class _Resp:
        status_code = 200
        text = ""
        def json(self):
            return {
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1},
            }

    class _Client:
        def __init__(self, *a, **kw): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *a): return None
        async def post(self, url, headers=None, json=None):
            captured["json"] = json
            return _Resp()

    import httpx as _httpx
    monkeypatch.setattr(_httpx, "AsyncClient", _Client)

    raw = "PAN ABCDE1234F should pass through with opt-out."
    await ai.call_llm(user_message=raw, redact_pii=False)

    sent = captured["json"]["messages"][-1]["content"]
    assert "ABCDE1234F" in sent  # not redacted when opted out
