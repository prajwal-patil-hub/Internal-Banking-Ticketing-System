"""Attachments that belong to a reply, and who may see them.

The rule worth pinning: an internal note is invisible to the person who raised
the ticket, so anything attached to it has to be invisible too. Filtering the
note but serving its file would leak exactly the content the flag exists to
withhold — and in practice the file is the sensitive part.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from app.api.v1.routes.tickets import (
    _attachment_is_internal,
    _serialize_attachment,
    _visible_attachments,
)


def _user(role: str, *, is_super_admin: bool = False) -> SimpleNamespace:
    return SimpleNamespace(
        id=uuid.uuid4(),
        role=SimpleNamespace(name=role),
        is_super_admin=is_super_admin,
    )


def _attachment(*, comment=None) -> SimpleNamespace:
    """Enough of an Attachment for the visibility helpers."""
    return SimpleNamespace(
        id=uuid.uuid4(),
        ticket_id=uuid.uuid4(),
        comment_id=getattr(comment, "id", None),
        comment=comment,
        original_filename="statement.pdf",
        content_type="application/pdf",
        size_bytes=2048,
        checksum_sha256="a" * 64,
        uploader=None,
        created_at=SimpleNamespace(isoformat=lambda: "2026-08-11T00:00:00+00:00"),
    )


def _comment(*, internal: bool) -> SimpleNamespace:
    return SimpleNamespace(id=uuid.uuid4(), is_internal=internal)


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def test_a_file_on_an_internal_note_is_internal() -> None:
    assert _attachment_is_internal(_attachment(comment=_comment(internal=True)))


def test_a_file_on_a_public_reply_is_not_internal() -> None:
    assert not _attachment_is_internal(_attachment(comment=_comment(internal=False)))


def test_a_file_on_the_ticket_itself_is_not_internal() -> None:
    """Evidence the customer sent in has no comment, and must stay visible."""
    assert not _attachment_is_internal(_attachment())


# ---------------------------------------------------------------------------
# Visibility — the leak this guards against
# ---------------------------------------------------------------------------

def test_branch_user_never_sees_a_file_from_an_internal_note() -> None:
    hidden = _attachment(comment=_comment(internal=True))
    visible = _attachment(comment=_comment(internal=False))
    own = _attachment()

    result = _visible_attachments([hidden, visible, own], _user("branch_user"))

    assert hidden not in result
    assert visible in result and own in result


@pytest.mark.parametrize("role", ["agent", "supervisor", "admin", "auditor"])
def test_staff_see_internal_files(role: str) -> None:
    """Including the auditor: read-only is about writing, not about scope."""
    rows = [_attachment(comment=_comment(internal=True)), _attachment()]

    assert _visible_attachments(rows, _user(role)) == rows


def test_a_branch_user_marked_super_admin_is_still_filtered() -> None:
    """The flag widens administrative reach, not the customer's own view."""
    hidden = _attachment(comment=_comment(internal=True))

    result = _visible_attachments([hidden], _user("branch_user", is_super_admin=True))

    assert result == []


def test_filtering_an_empty_list_is_fine() -> None:
    assert _visible_attachments([], _user("branch_user")) == []


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------

def test_reply_files_carry_their_comment_id() -> None:
    """The UI needs it to render the file under the right reply."""
    comment = _comment(internal=False)

    payload = _serialize_attachment(_attachment(comment=comment))

    assert payload["comment_id"] == str(comment.id)


def test_ticket_files_report_a_null_comment_id() -> None:
    assert _serialize_attachment(_attachment())["comment_id"] is None


def test_serialised_payload_exposes_no_storage_location() -> None:
    """The S3 key must not reach the client — it is the one thing that would
    make a stolen response useful against the bucket directly."""
    payload = _serialize_attachment(_attachment())

    assert "s3_key" not in payload
    assert "s3_bucket" not in payload
