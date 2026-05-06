"""S3-compatible storage adapter (MinIO in dev, Supabase/AWS in prod).

Stores ticket attachments under deterministic, ticket-scoped keys so that
even if a metadata row is lost the file is locatable. Returns the storage
key + sha256 checksum so the caller can persist them.
"""

from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from typing import BinaryIO

import boto3
from botocore.client import Config

from app.core.config import settings
from app.core.logging import get_logger

log = get_logger(__name__)


@dataclass(slots=True)
class StoredObject:
    storage_key: str
    size_bytes: int
    checksum_sha256: str


class StorageAdapter:
    def __init__(self) -> None:
        self._client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            region_name=settings.S3_REGION,
            config=Config(signature_version="s3v4"),
        )
        self._bucket = settings.S3_BUCKET

    def ensure_bucket(self) -> None:
        existing = {b["Name"] for b in self._client.list_buckets().get("Buckets", [])}
        if self._bucket not in existing:
            self._client.create_bucket(Bucket=self._bucket)
            log.info("storage_bucket_created", bucket=self._bucket)

    def put_attachment(
        self,
        *,
        ticket_id: uuid.UUID,
        file_name: str,
        content_type: str,
        body: bytes,
    ) -> StoredObject:
        if not body:
            raise ValueError("Empty file rejected.")
        digest = hashlib.sha256(body).hexdigest()
        key = f"tickets/{ticket_id}/{uuid.uuid4().hex}_{file_name}"
        self._client.put_object(
            Bucket=self._bucket,
            Key=key,
            Body=body,
            ContentType=content_type,
            Metadata={"sha256": digest, "original_name": file_name},
        )
        return StoredObject(storage_key=key, size_bytes=len(body), checksum_sha256=digest)

    def open_attachment(self, storage_key: str) -> BinaryIO:
        obj = self._client.get_object(Bucket=self._bucket, Key=storage_key)
        return obj["Body"]
