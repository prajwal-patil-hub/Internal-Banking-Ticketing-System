"""Attachment storage: upload validation, key naming, and the S3 round trip.

The round-trip tests run against moto rather than a live MinIO, so the suite
needs no container to prove the bytes survive.
"""

from __future__ import annotations

import uuid

import pytest

from app.core.exceptions import ValidationError
from app.services.storage_service import (
    ALLOWED_CONTENT_TYPES,
    MAX_UPLOAD_BYTES,
    build_key,
    sanitize_filename,
    validate_upload,
)


# ---------------------------------------------------------------------------
# Filename sanitising
# ---------------------------------------------------------------------------

def test_directory_traversal_is_stripped_to_a_bare_name() -> None:
    """The name is echoed in a download header, so it must carry no path."""
    assert sanitize_filename("../../etc/passwd") == "passwd"
    assert sanitize_filename("..\\..\\windows\\system32\\cmd.exe") == "cmd.exe"


def test_ordinary_names_survive_intact() -> None:
    assert sanitize_filename("Statement_2026-08.pdf") == "Statement_2026-08.pdf"


def test_awkward_characters_are_replaced_not_dropped() -> None:
    cleaned = sanitize_filename("my report (final);rm -rf.pdf")

    assert "/" not in cleaned and ";" not in cleaned and " " not in cleaned
    assert cleaned.endswith(".pdf")


def test_a_name_with_nothing_usable_still_yields_something() -> None:
    assert sanitize_filename("///") == "file"
    assert sanitize_filename("") == "file"


def test_long_names_are_truncated() -> None:
    assert len(sanitize_filename("a" * 500 + ".pdf")) <= 120


# ---------------------------------------------------------------------------
# Upload validation
# ---------------------------------------------------------------------------

def test_accepted_types_return_their_extension() -> None:
    assert validate_upload("s.pdf", "application/pdf", 1024) == "pdf"
    assert validate_upload("s.png", "image/png", 1024) == "png"


def test_charset_parameter_does_not_defeat_the_check() -> None:
    """Browsers send `text/plain; charset=utf-8` — matching the raw string fails."""
    assert validate_upload("notes.txt", "text/plain; charset=utf-8", 10) == "txt"


def test_uppercase_content_type_is_accepted() -> None:
    assert validate_upload("s.pdf", "APPLICATION/PDF", 10) == "pdf"


@pytest.mark.parametrize(
    "content_type",
    [
        "application/x-msdownload",   # .exe
        "application/zip",            # unscanned archive
        "application/x-sh",
        "text/html",                  # stored XSS if ever served inline
        "",
    ],
)
def test_dangerous_or_unknown_types_are_refused(content_type: str) -> None:
    with pytest.raises(ValidationError):
        validate_upload("payload", content_type, 1024)


def test_empty_file_is_refused() -> None:
    with pytest.raises(ValidationError):
        validate_upload("empty.pdf", "application/pdf", 0)


def test_oversized_file_is_refused_with_a_readable_message() -> None:
    with pytest.raises(ValidationError) as excinfo:
        validate_upload("huge.pdf", "application/pdf", MAX_UPLOAD_BYTES + 1)

    # The message should tell the user the limit, not just say "too large".
    assert "15 MB" in str(excinfo.value)


def test_the_size_limit_boundary_is_inclusive() -> None:
    assert validate_upload("exact.pdf", "application/pdf", MAX_UPLOAD_BYTES) == "pdf"


# ---------------------------------------------------------------------------
# Key construction
# ---------------------------------------------------------------------------

def test_keys_are_namespaced_by_ticket_and_never_collide() -> None:
    ticket = uuid.uuid4()

    first = build_key(ticket, "pdf")
    second = build_key(ticket, "pdf")

    assert first.startswith(f"tickets/{ticket}/")
    assert first.endswith(".pdf")
    # Two uploads of the same filename must not overwrite one another.
    assert first != second


def test_the_key_leaks_nothing_about_the_original_filename() -> None:
    key = build_key(uuid.uuid4(), "pdf")

    assert "statement" not in key.lower()


# ---------------------------------------------------------------------------
# S3 round trip, against moto
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_upload_download_delete_round_trip(monkeypatch) -> None:
    moto = pytest.importorskip("moto")

    from app.core.config import settings
    from app.services.storage_service import StorageService

    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1", raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET", "round-trip-bucket", raising=False)

    payload = b"%PDF-1.4 pretend statement"
    key = build_key(uuid.uuid4(), "pdf")

    with moto.mock_aws():
        service = StorageService()

        # ensure_bucket runs implicitly — a fresh volume has no bucket yet.
        stored = await service.upload(key, payload, "application/pdf")
        assert stored.size_bytes == len(payload)

        assert await service.download(key) == payload

        await service.delete(key)
        with pytest.raises(Exception):
            await service.download(key)


@pytest.mark.asyncio
async def test_deleting_a_missing_object_does_not_raise(monkeypatch) -> None:
    """The DB row is going either way; failing here would strand it."""
    moto = pytest.importorskip("moto")

    from app.core.config import settings
    from app.services.storage_service import StorageService

    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1", raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET", "missing-object-bucket", raising=False)

    with moto.mock_aws():
        service = StorageService()
        await service.ensure_bucket()

        await service.delete("tickets/none/does-not-exist.pdf")  # must not raise


@pytest.mark.asyncio
async def test_checksum_matches_the_bytes_uploaded(monkeypatch) -> None:
    import hashlib

    moto = pytest.importorskip("moto")

    from app.core.config import settings
    from app.services.storage_service import StorageService

    monkeypatch.setattr(settings, "S3_ENDPOINT_URL", None, raising=False)
    monkeypatch.setattr(settings, "S3_ACCESS_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_SECRET_KEY", "testing", raising=False)
    monkeypatch.setattr(settings, "S3_REGION", "us-east-1", raising=False)
    monkeypatch.setattr(settings, "S3_BUCKET", "checksum-bucket", raising=False)

    payload = b"integrity matters"

    with moto.mock_aws():
        stored = await StorageService().upload(
            build_key(uuid.uuid4(), "txt"), payload, "text/plain"
        )

    assert stored.checksum_sha256 == hashlib.sha256(payload).hexdigest()


def test_no_executable_type_slipped_into_the_allow_list() -> None:
    """A guard against a future 'just add zip' edit."""
    forbidden = {"zip", "exe", "sh", "js", "html", "svg"}

    assert not forbidden & set(ALLOWED_CONTENT_TYPES.values())
