"""Upload → validate → store → parse → chunk → embed → activate.

The invariant this service exists to protect: **a document is never partially
retrievable.** A half-embedded version answering questions is worse than one
that is missing, because it produces confident answers that cite half a policy.

That is enforced by splitting ingestion into two committed phases:

*Phase 1* creates the document and version rows with status `PENDING` and puts
the bytes in object storage, then commits. From this moment the upload is
visible in the admin UI and the operator can see something is happening.

*Phase 2* parses, chunks and embeds. Only when every chunk has a vector does
the version flip to `READY` and `kb_documents.active_version_id` move to point
at it. If anything fails, the version is marked `FAILED` with the reason and
the *previous* active version keeps serving — a bad re-index degrades to "the
new copy didn't take", never to "the document half-disappeared".

Ingestion runs inline in the request rather than on the APScheduler workers.
That is a deliberate scope decision, not an oversight: a background job needs
its own queue table, retry policy and orphan-recovery sweep, and a PENDING row
stranded by a process restart is a worse failure than a slow upload. The
phase split and the status column are exactly the machinery a worker would
need, so moving it later is a change in one place. Until then
`KB_MAX_UPLOAD_BYTES` is what keeps the request bounded.
"""

from __future__ import annotations

import hashlib
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ValidationError
from app.core.logging import get_logger
from app.models.knowledge import (
    KBChunk,
    KBCollection,
    KBDocument,
    KBDocumentVersion,
    KBVersionStatus,
)
from app.models.user import User
from app.services import llm_client
from app.services.kb_chunking import chunk_blocks
from app.services.kb_parsing import SUPPORTED_EXTENSIONS, parse
from app.services.storage_service import StorageService, sanitize_filename

log = get_logger(__name__)

#: What a knowledge base legitimately holds. Narrower than the attachment
#: allowlist on purpose: images are accepted as ticket evidence but cannot be
#: read by this pipeline, and storing something unparseable would create a
#: document that exists and never retrieves.
KB_CONTENT_TYPES: dict[str, str] = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
    "text/plain": "txt",
    "text/markdown": "md",
    "text/csv": "csv",
}

#: Texts sent to the embedding model per HTTP call. Large enough to amortise
#: the round trip, small enough that one failure does not lose a whole book.
EMBED_BATCH_SIZE = 16


def validate_kb_upload(filename: str, content_type: str, size: int) -> str:
    """Check the file can be indexed and return its canonical extension."""
    if size <= 0:
        raise ValidationError("The file is empty.")
    if size > settings.KB_MAX_UPLOAD_BYTES:
        raise ValidationError(
            f"File is {size / 1_048_576:.1f} MB — the knowledge-base limit is "
            f"{settings.KB_MAX_UPLOAD_BYTES // 1_048_576} MB."
        )

    normalised = (content_type or "").split(";")[0].strip().lower()
    ext = KB_CONTENT_TYPES.get(normalised)

    # Browsers send text/markdown inconsistently (often text/plain, sometimes
    # application/octet-stream), so fall back to the filename for the text
    # formats only — never for PDF/DOCX, where the bytes matter.
    if ext is None:
        suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if suffix in {"md", "txt", "csv"}:
            ext = suffix

    if ext is None or ext not in SUPPORTED_EXTENSIONS:
        raise ValidationError(
            f"'{normalised or 'unknown'}' files cannot be indexed. Upload a "
            f"PDF, Word document, Markdown, plain-text or CSV file."
        )
    return ext


def build_kb_key(collection_id: uuid.UUID, extension: str) -> str:
    """`kb/<collection>/<random>.<ext>`.

    A separate prefix from `tickets/` so the existing backup and restore
    tooling covers knowledge-base documents with no new machinery, while a
    prefix-scoped delete still only ever touches one collection.
    """
    return f"kb/{collection_id}/{uuid.uuid4().hex}.{extension}"


class KBIngestionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.storage = StorageService()

    # -- phase 1 -----------------------------------------------------------

    async def create_version(
        self,
        *,
        collection: KBCollection,
        filename: str,
        content_type: str,
        data: bytes,
        user: User,
        title: str | None = None,
        document: KBDocument | None = None,
        force_new_version: bool = False,
    ) -> tuple[KBDocument, KBDocumentVersion, bool]:
        """Store the bytes and register a pending version.

        Returns `(document, version, is_duplicate)`. When the identical bytes
        are already the active version of this document, nothing is stored or
        re-embedded and `is_duplicate` is True — re-uploading an unchanged file
        is a no-op rather than a second copy of every vector.
        """
        ext = validate_kb_upload(filename, content_type, len(data))
        checksum = hashlib.sha256(data).hexdigest()
        safe_name = sanitize_filename(filename)

        # Re-indexing deliberately re-uploads identical bytes, so it needs the
        # dedupe short-circuit skipped or it would return the very version it
        # is trying to replace.
        if document is not None and not force_new_version:
            existing = (
                await self.db.execute(
                    select(KBDocumentVersion).where(
                        KBDocumentVersion.document_id == document.id,
                        KBDocumentVersion.checksum_sha256 == checksum,
                        KBDocumentVersion.status == KBVersionStatus.READY.value,
                    )
                )
            ).scalar_one_or_none()
            if existing is not None:
                log.info(
                    "kb.duplicate_upload_ignored",
                    document_id=str(document.id),
                    checksum=checksum[:12],
                )
                return document, existing, True

        if document is None:
            document = KBDocument(
                collection_id=collection.id,
                title=(title or safe_name)[:255],
                original_filename=safe_name,
                content_type=content_type,
                uploaded_by_id=user.id,
            )
            self.db.add(document)
            await self.db.flush()

        next_no = (
            await self.db.execute(
                select(func.coalesce(func.max(KBDocumentVersion.version_no), 0) + 1).where(
                    KBDocumentVersion.document_id == document.id
                )
            )
        ).scalar_one()

        key = build_kb_key(collection.id, ext)
        stored = await self.storage.upload(key, data, content_type)

        version = KBDocumentVersion(
            document_id=document.id,
            version_no=next_no,
            s3_key=stored.key,
            s3_bucket=stored.bucket,
            size_bytes=stored.size_bytes,
            checksum_sha256=checksum,
            status=KBVersionStatus.PENDING.value,
            embedding_model=settings.KB_EMBEDDING_MODEL,
            created_by_id=user.id,
        )
        self.db.add(version)
        await self.db.commit()
        await self.db.refresh(version)
        await self.db.refresh(document)
        return document, version, False

    # -- phase 2 -----------------------------------------------------------

    async def process_version(
        self, document: KBDocument, version: KBDocumentVersion, *, extension: str
    ) -> KBDocumentVersion:
        """Parse, chunk, embed and activate. Marks FAILED on any error."""
        version.status = KBVersionStatus.PROCESSING.value
        await self.db.commit()

        try:
            data = await self.storage.download(version.s3_key)
            parsed = parse(data, extension, version.s3_key)

            chunks = chunk_blocks(
                parsed.blocks,
                max_chars=settings.KB_CHUNK_CHARS,
                overlap_chars=settings.KB_CHUNK_OVERLAP_CHARS,
            )
            if not chunks:
                raise ValidationError(
                    "No indexable text was found in this file, so there is "
                    "nothing to retrieve. Check the document is not empty."
                )
            if len(chunks) > settings.KB_MAX_CHUNKS_PER_DOCUMENT:
                raise ValidationError(
                    f"This document produces {len(chunks):,} passages, over the "
                    f"{settings.KB_MAX_CHUNKS_PER_DOCUMENT:,} limit. Embedding it "
                    "would occupy the local model long enough to stall chat and "
                    "email intake. Split it into smaller documents."
                )

            rows: list[KBChunk] = []
            for chunk in chunks:
                rows.append(
                    KBChunk(
                        version_id=version.id,
                        document_id=document.id,
                        # Denormalised security key — see models/knowledge.py.
                        collection_id=document.collection_id,
                        ordinal=chunk.ordinal,
                        heading_path=chunk.heading_path,
                        content=chunk.content,
                        char_count=chunk.char_count,
                        page_from=chunk.page_from,
                        page_to=chunk.page_to,
                    )
                )
            self.db.add_all(rows)
            await self.db.flush()

            embedded = 0
            for start in range(0, len(chunks), EMBED_BATCH_SIZE):
                batch = chunks[start : start + EMBED_BATCH_SIZE]
                vectors = await llm_client.embed([c.embedding_text() for c in batch])
                if len(vectors) != len(batch):
                    raise llm_client.EmbeddingError(
                        f"Embedding model returned {len(vectors)} vectors for "
                        f"{len(batch)} passages."
                    )
                for row, vector in zip(rows[start : start + len(batch)], vectors, strict=True):
                    row.embedding = vector
                embedded += len(batch)

            version.chunk_count = len(chunks)
            version.embedded_count = embedded
            version.page_count = parsed.page_count

            # The activation gate. Everything above can succeed partially; this
            # is the only place the version becomes visible to retrieval, and it
            # only fires when every chunk carries a vector.
            if embedded != len(chunks):
                raise llm_client.EmbeddingError(
                    f"Only {embedded} of {len(chunks)} passages were embedded."
                )

            version.status = KBVersionStatus.READY.value
            version.activated_at = func.now()
            version.error_message = None
            document.active_version_id = version.id
            await self.db.commit()
            await self.db.refresh(version)

            log.info(
                "kb.version_activated",
                document_id=str(document.id),
                version_id=str(version.id),
                chunks=len(chunks),
                pages=parsed.page_count,
            )
            return version

        except Exception as exc:
            # Read the identifiers BEFORE rolling back. `rollback()` expires
            # every object in the session, so touching `version.id` afterwards
            # triggers a synchronous lazy load and raises MissingGreenlet from
            # inside the error handler — the failure path would then crash
            # instead of marking the version FAILED, and the document would sit
            # in PROCESSING for ever. A mocked session never expires anything,
            # which is why only a real database surfaced this.
            version_id = version.id
            document_id = document.id

            # Discard the half-written chunk rows, then record the failure on a
            # clean session. The previous active version is untouched, so the
            # collection keeps answering from the last good copy.
            await self.db.rollback()
            failed = await self.db.get(KBDocumentVersion, version_id)
            if failed is not None:
                failed.status = KBVersionStatus.FAILED.value
                failed.error_message = str(exc)[:2000]
                await self.db.commit()
                await self.db.refresh(failed)
            log.warning(
                "kb.ingestion_failed",
                # Captured ids, not the expired ORM objects — see above.
                document_id=str(document_id),
                version_id=str(version_id),
                error=str(exc),
            )
            raise

    async def ingest(
        self,
        *,
        collection: KBCollection,
        filename: str,
        content_type: str,
        data: bytes,
        user: User,
        title: str | None = None,
        document: KBDocument | None = None,
    ) -> tuple[KBDocument, KBDocumentVersion, bool]:
        """Both phases. The common path callers want."""
        ext = validate_kb_upload(filename, content_type, len(data))
        document, version, duplicate = await self.create_version(
            collection=collection,
            filename=filename,
            content_type=content_type,
            data=data,
            user=user,
            title=title,
            document=document,
        )
        if duplicate:
            return document, version, True
        version = await self.process_version(document, version, extension=ext)
        return document, version, False

    async def delete_document(self, document: KBDocument) -> None:
        """Remove a document, its versions, its chunks and its stored bytes.

        Storage objects are deleted after the row, and a storage failure is
        logged rather than raised: an orphaned object costs disk, whereas a
        failed delete that leaves the row would keep the document retrievable
        after an administrator was told it was gone.
        """
        keys = [v.s3_key for v in document.versions]
        await self.db.delete(document)
        await self.db.commit()

        for key in keys:
            try:
                await self.storage.delete(key)
            except Exception as exc:  # pragma: no cover - storage best effort
                log.warning("kb.object_delete_failed", key=key, error=str(exc))
