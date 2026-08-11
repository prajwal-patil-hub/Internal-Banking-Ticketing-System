"""Header parsing for inbound mail.

These cover the shapes real mail arrives in — display names, MIME-encoded
subjects, multipart bodies, missing headers — because the parser is the one
place a malformed message can quietly corrupt a ticket.
"""

from __future__ import annotations

from app.services.email_service import _parse_raw_email


def _raw(headers: str, body: str = "Body text here.\n") -> bytes:
    return (headers.strip() + "\n\n" + body).encode()


BASIC = """\
From: Priya Customer <priya@example.com>
To: SUCCESS Support <support@bank.example>
Subject: Card blocked
Message-ID: <abc-1@example.com>
Date: Tue, 11 Aug 2026 09:12:00 +0000
"""


def test_display_name_is_split_from_the_address() -> None:
    """`From: Name <addr>` must not leave the name inside from_address.

    Anything treating the field as an address — the domain check, a reply's
    To: header — breaks if the two stay joined.
    """
    parsed = _parse_raw_email(_raw(BASIC))

    assert parsed["from_address"] == "priya@example.com"
    assert parsed["from_name"] == "Priya Customer"
    assert parsed["to_address"] == "support@bank.example"


def test_bare_address_without_a_display_name() -> None:
    parsed = _parse_raw_email(_raw("From: priya@example.com\nTo: s@bank.example\n"
                                   "Subject: Hi\nMessage-ID: <b@x>\n"))

    assert parsed["from_address"] == "priya@example.com"
    assert parsed["from_name"] is None


def test_sender_domain_is_lowercased() -> None:
    """Domains are case-insensitive; storing the raw case defeats grouping."""
    parsed = _parse_raw_email(_raw("From: P <priya@Example.COM>\nTo: s@bank.example\n"
                                   "Subject: Hi\nMessage-ID: <c@x>\n"))

    assert parsed["sender_domain"] == "example.com"


def test_cc_list_is_split_on_commas() -> None:
    parsed = _parse_raw_email(_raw(BASIC + "Cc: a@example.com, b@example.com\n"))

    assert parsed["cc_addresses"] == ["a@example.com", "b@example.com"]


def test_absent_cc_is_none_not_an_empty_list() -> None:
    """None distinguishes "no Cc header" from "a Cc header we failed to read"."""
    assert _parse_raw_email(_raw(BASIC))["cc_addresses"] is None


def test_mime_encoded_subject_is_decoded() -> None:
    parsed = _parse_raw_email(_raw(
        "From: p@example.com\nTo: s@bank.example\n"
        "Subject: =?utf-8?B?Q2FyZCBibG9ja2Vk?=\nMessage-ID: <d@x>\n"
    ))

    assert parsed["subject"] == "Card blocked"


def test_reply_is_flagged_and_threaded_to_the_original() -> None:
    parsed = _parse_raw_email(_raw(
        "From: p@example.com\nTo: s@bank.example\nSubject: Re: Card blocked\n"
        "Message-ID: <e-2@x>\nIn-Reply-To: <e-1@x>\nReferences: <e-1@x>\n"
    ))

    assert parsed["is_reply"] is True
    assert parsed["in_reply_to"] == "<e-1@x>"
    # The thread is named by its root, so every later reply lands in one place.
    assert parsed["thread_id"] == "<e-1@x>"


def test_first_message_threads_under_its_own_id() -> None:
    parsed = _parse_raw_email(_raw(BASIC))

    assert parsed["is_reply"] is False
    assert parsed["thread_id"] == "<abc-1@example.com>"


def test_spf_pass_and_fail_are_read_from_the_mta_header() -> None:
    passed = _parse_raw_email(_raw(BASIC + "Received-SPF: pass (bank.example: ok)\n"))
    failed = _parse_raw_email(_raw(BASIC + "Received-SPF: softfail (bank.example: bad)\n"))

    assert passed["spf_pass"] is True
    assert failed["spf_pass"] is False
    # No header at all is unknown, which is not the same as a failure.
    assert _parse_raw_email(_raw(BASIC))["spf_pass"] is None


def test_multipart_body_prefers_the_plain_text_part() -> None:
    raw = (
        "From: p@example.com\nTo: s@bank.example\nSubject: Multi\n"
        "Message-ID: <f@x>\n"
        'Content-Type: multipart/alternative; boundary="BOUND"\n'
        "\n"
        "--BOUND\nContent-Type: text/plain; charset=utf-8\n\n"
        "The plain version.\n"
        "--BOUND\nContent-Type: text/html; charset=utf-8\n\n"
        "<p>The HTML version.</p>\n"
        "--BOUND--\n"
    ).encode()

    parsed = _parse_raw_email(raw)

    assert "The plain version." in parsed["body_text"]
    assert "HTML version" in parsed["body_html"]


def test_attachments_are_counted() -> None:
    raw = (
        "From: p@example.com\nTo: s@bank.example\nSubject: With file\n"
        "Message-ID: <g@x>\n"
        'Content-Type: multipart/mixed; boundary="B"\n'
        "\n"
        "--B\nContent-Type: text/plain\n\nSee attached.\n"
        "--B\nContent-Type: application/pdf\n"
        'Content-Disposition: attachment; filename="statement.pdf"\n\n'
        "%PDF-1.4\n"
        "--B--\n"
    ).encode()

    assert _parse_raw_email(raw)["attachments_count"] == 1


def test_missing_date_falls_back_to_now_rather_than_raising() -> None:
    """A malformed Date must not cost us the message."""
    parsed = _parse_raw_email(_raw("From: p@example.com\nTo: s@bank.example\n"
                                   "Subject: No date\nMessage-ID: <h@x>\n"
                                   "Date: not-a-real-date\n"))

    assert parsed["received_at"] is not None
