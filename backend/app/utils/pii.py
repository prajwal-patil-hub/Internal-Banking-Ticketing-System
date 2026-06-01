"""PII redaction for any text leaving the bank network.

Applied to every LLM prompt (chat, summarize, suggest, categorize). The
output replaces matched spans with ``[REDACTED_<TYPE>]`` markers so the
downstream model still sees the structural context — "the customer's
[REDACTED_AADHAAR] failed verification" — without learning the secret.

Patterns are India-banking-centric (PAN, Aadhaar, IFSC, UPI, +91 phones)
plus universal ones (email, generic card, generic long-digit account).
Order matters: more-specific patterns run before broader fallbacks so
e.g. a card number isn't first chopped into "account-shaped" fragments.

This is intentionally conservative — false positives (over-redaction) are
strictly preferred to false negatives (a real PAN leaving the network).
If a regex starts hurting AI quality, tighten it; never widen it without
a compliance review.
"""

from __future__ import annotations

import re
from typing import NamedTuple


class RedactionReport(NamedTuple):
    text: str
    counts: dict[str, int]   # {"pan": 1, "phone": 2, ...}

    @property
    def total(self) -> int:
        return sum(self.counts.values())


# (name, compiled pattern, replacement). Order = priority.
#
# Ordering rules that were each load-bearing for a real test failure:
#   1. email before upi   — UPI handle (`x@psp`) has no TLD dot; email needs one.
#   2. card  before aadhaar — a 16-digit card with spaces contains an
#      Aadhaar-shaped prefix; the card rule must consume it whole.
#   3. card  requires separators — otherwise a 14-digit bare account number
#      gets mis-tagged as a card. Bare runs fall through to "account".
#   4. upi   before phone  — a UPI handle like `9876543210@ybl` contains a
#      phone-shaped substring; phone must not eat the digits in isolation.
_PATTERNS: list[tuple[str, re.Pattern[str], str]] = [
    # Email — runs before UPI.
    (
        "email",
        re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"),
        "[REDACTED_EMAIL]",
    ),
    # PAN — fixed shape: 5 letters + 4 digits + 1 letter.
    (
        "pan",
        re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b"),
        "[REDACTED_PAN]",
    ),
    # Credit/debit card — REQUIRES separators between four groups so it
    # can't swallow bare account numbers. Total 13-19 digits.
    (
        "card",
        re.compile(r"\b\d{4}[\s-]\d{4}[\s-]\d{4}[\s-]\d{1,7}\b"),
        "[REDACTED_CARD]",
    ),
    # Aadhaar — 12 digits, optional spaces/hyphens in groups of 4. The
    # negative lookahead stops it from biting off the first 12 digits of a
    # 16-digit card when the card rule above didn't match (rare but possible).
    (
        "aadhaar",
        re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b(?![\s-]?\d)"),
        "[REDACTED_AADHAAR]",
    ),
    # CVV — explicit context only ("cvv 123", "cvv: 1234"). Bare 3-digit
    # numbers in normal prose are too noisy to redact safely.
    (
        "cvv",
        re.compile(r"\bcvv[\s:]+\d{3,4}\b", re.IGNORECASE),
        "[REDACTED_CVV]",
    ),
    # IFSC — 4 letters + 0 + 6 alphanumerics.
    (
        "ifsc",
        re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b"),
        "[REDACTED_IFSC]",
    ),
    # UPI handle — local@psp where psp is short. Real emails were already
    # consumed by the email rule above (it requires a TLD dot), so anything
    # `@psp` reaching here is a UPI handle.
    # Must run before phone so phone doesn't grab the digit-only local part.
    (
        "upi",
        re.compile(r"\b[A-Za-z0-9._\-]+@[a-z]{2,12}\b"),
        "[REDACTED_UPI]",
    ),
    # Indian phone — optional +91 / 0, then 10 digits starting 6-9.
    (
        "phone",
        re.compile(r"\b(?:\+?91[\s-]?|0)?[6-9]\d{4}[\s-]?\d{5}\b"),
        "[REDACTED_PHONE]",
    ),
    # Generic long-digit account fallback — 10-18 contiguous digits.
    (
        "account",
        re.compile(r"\b\d{10,18}\b"),
        "[REDACTED_ACCOUNT]",
    ),
]


def redact_pii(text: str) -> RedactionReport:
    """Replace recognised PII spans with placeholder markers.

    Returns the redacted text and a per-type count for audit logging.
    ``None`` input is treated as empty string so callers can pass model
    fields directly.
    """
    if not text:
        return RedactionReport(text=text or "", counts={})

    counts: dict[str, int] = {}
    out = text
    for name, pattern, replacement in _PATTERNS:
        out, n = pattern.subn(replacement, out)
        if n:
            counts[name] = n
    return RedactionReport(text=out, counts=counts)


def redact_message_list(messages: list[dict]) -> tuple[list[dict], dict[str, int]]:
    """Apply redaction to a list of {role, content} dicts.

    Returns the new list and aggregated counts. Non-string content is
    passed through unchanged (multimodal payloads aren't redacted here).
    """
    aggregate: dict[str, int] = {}
    out: list[dict] = []
    for m in messages:
        content = m.get("content")
        if isinstance(content, str):
            r = redact_pii(content)
            new_m = dict(m)
            new_m["content"] = r.text
            out.append(new_m)
            for k, v in r.counts.items():
                aggregate[k] = aggregate.get(k, 0) + v
        else:
            out.append(m)
    return out, aggregate
