"""S3-compatible object storage for ticket attachments.

MinIO has been in the stack since P0 and boto3 in the dependencies, but nothing
ever wrote a byte to it: the Attachment model, the ticket relationship and the
bucket all existed with no code between them.

Two decisions worth stating:

**Files stream through the API rather than via presigned URLs.** A presigned
URL is faster and cheaper, but it is a bearer token in a query string — it
outlives the session, survives in browser history and proxy logs, and grants
access to anyone holding it. For bank documents, where the whole point is that
only people with rights to the ticket can read the attachment, every request
goes through the permission check instead.

**Keys are namespaced by ticket and randomised.** `tickets/<id>/<uuid>.<ext>`
means a leaked key reveals nothing about the file, two uploads of `statement.pdf`
never collide, and deleting a ticket's objects is a prefix operation.
"""

from __future__ import annotations

import hashlib
import re
import uuid
from dataclasses import dataclass

from app.core.config import settings
from app.core.exceptions import StorageUnavailableError, ValidationError
from app.core.logging import get_logger

log = get_logger(__name__)

#: Largest single upload. Big enough for a scanned statement, small enough that
#: one user cannot fill the volume with a single request.
MAX_UPLOAD_BYTES = 15 * 1024 * 1024

#: What a support ticket legitimately needs: evidence and documents. Executables
#: and archives are refused outright rather than scanned, because there is no
#: malware scanner here and an unscanned archive is the classic delivery route.
ALLOWED_CONTENT_TYPES: dict[str, str] = {
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/gif": "gif",
    "image/webp": "webp",
    "application/pdf": "pdf",
    "text/plain": "txt",
    "text/csv": "csv",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "xlsx",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "application/msword": "doc",
    "application/vnd.ms-excel": "xls",
}

_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def _is_unreachable(exc: Exception) -> bool:
    """True when the failure is "the store is down", not "that request was bad".

    Matched on botocore's exception classes rather than the message, so a
    missing key or a permission error still surfaces as itself. Imported
    lazily because boto3 is only loaded when storage is actually used.
    """
    try:
        from botocore.exceptions import (
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            NoCredentialsError,
        )
    except ImportError:  # pragma: no cover - boto3 is a hard dependency
        return False

    return isinstance(
        exc,
        EndpointConnectionError
        | ConnectTimeoutError
        | ConnectionClosedError
        | NoCredentialsError,
    )


@dataclass
class StoredObject:
    key: str
    bucket: str
    size_bytes: int
    checksum_sha256: str


def sanitize_filename(name: str) -> str:
    """Make a client-supplied filename safe to store and echo back.

    Strips any directory component before sanitising: a name like
    `../../etc/passwd` must not survive as a path, and it is the download
    header where a raw name would otherwise be reflected.
    """
    base = (name or "file").replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "file"
    return cleaned[:120]


def validate_upload(filename: str, content_type: str, size: int) -> str:
    """Check the file is acceptable and return its canonical extension."""
    if size <= 0:
        raise ValidationError("The file is empty.")
    if size > MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File is {size / 1_048_576:.1f} MB — the limit is "
            f"{MAX_UPLOAD_BYTES // 1_048_576} MB."
        )

    normalised = (content_type or "").split(";")[0].strip().lower()
    if normalised not in ALLOWED_CONTENT_TYPES:
        raise ValidationError(
            f"'{normalised or 'unknown'}' files are not accepted. "
            f"Allowed: images, PDF, text, CSV and Office documents."
        )
    return ALLOWED_CONTENT_TYPES[normalised]


def build_key(ticket_id: uuid.UUID, extension: str) -> str:
    """`tickets/<ticket>/<random>.<ext>` — see the module docstring."""
    return f"tickets/{ticket_id}/{uuid.uuid4().hex}.{extension}"


class StorageService:
    """Thin wrapper over the S3 API.

    boto3 is synchronous, so every call is pushed to a thread — blocking the
    event loop on a 15 MB upload would stall every other request on the worker.
    """

    def __init__(self) -> None:
        self._client = None

    def _s3(self):
        if self._client is None:
            import boto3
            from botocore.config import Config

            self._client = boto3.client(
                "s3",
                endpoint_url=settings.S3_ENDPOINT_URL,
                aws_access_key_id=settings.S3_ACCESS_KEY,
                aws_secret_access_key=settings.S3_SECRET_KEY,
                region_name=settings.S3_REGION,
                config=Config(signature_version="s3v4", retries={"max_attempts": 3}),
            )
        return self._client

    async def _run(self, func, *args, **kwargs):
        import asyncio

        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, lambda: func(*args, **kwargs))

    async def ensure_bucket(self) -> None:
        """Create the bucket if this is a fresh volume.

        MinIO starts empty, so the first upload after `down -v` would otherwise
        fail with NoSuchBucket — a confusing error for what is really a
        first-run condition.
        """
        client = self._s3()
        try:
            await self._run(client.head_bucket, Bucket=settings.S3_BUCKET)
        except Exception:
            try:
                await self._run(client.create_bucket, Bucket=settings.S3_BUCKET)
                log.info("storage.bucket_created", bucket=settings.S3_BUCKET)
            except Exception as exc:
                log.debug("storage.bucket_create_skipped", error=str(exc))

    async def upload(self, key: str, data: bytes, content_type: str) -> StoredObject:
        await self.ensure_bucket()
        checksum = hashlib.sha256(data).hexdigest()

        try:
            await self._run(
                self._s3().put_object,
                Bucket=settings.S3_BUCKET,
                Key=key,
                Body=data,
                ContentType=content_type,
                # Stored so integrity can be checked on the way back out; the
                # database keeps its own copy for the same reason.
                Metadata={"sha256": checksum},
            )
        except Exception as exc:
            if _is_unreachable(exc):
                log.error("storage.unreachable", operation="upload", error=str(exc))
                raise StorageUnavailableError() from exc
            raise
        log.info("storage.uploaded", key=key, size=len(data))
        return StoredObject(
            key=key,
            bucket=settings.S3_BUCKET,
            size_bytes=len(data),
            checksum_sha256=checksum,
        )

    async def download(self, key: str) -> bytes:
        try:
            response = await self._run(
                self._s3().get_object, Bucket=settings.S3_BUCKET, Key=key
            )
        except Exception as exc:
            if _is_unreachable(exc):
                log.error("storage.unreachable", operation="download", error=str(exc))
                raise StorageUnavailableError() from exc
            raise
        return await self._run(response["Body"].read)

    async def delete(self, key: str) -> None:
        """Remove an object. A missing object is not an error — the caller is
        deleting it either way, and failing here would strand the DB row."""
        try:
            await self._run(
                self._s3().delete_object, Bucket=settings.S3_BUCKET, Key=key
            )
            log.info("storage.deleted", key=key)
        except Exception as exc:
            log.warning("storage.delete_failed", key=key, error=str(exc))


#: One client for the process; boto3 clients are thread-safe and expensive to build.
storage = StorageService()
