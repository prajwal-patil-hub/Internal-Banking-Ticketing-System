"""Build the corpus the golden set is scored against.

Two decisions here, both of which took a wrong turn first.

**The corpus is pinned in the repo, not borrowed from the demo seed.** An
earlier version scored against whatever `seed_dev.py` happened to have loaded.
That makes the numbers meaningless across runs: someone edits a demo document
to make a screenshot look better, and retrieval recall moves for reasons
nobody can reconstruct. `evals/corpus/` is version-controlled beside the
questions that reference it, so a score change means the *system* changed.

**Ingestion here bypasses object storage.** The production path stores bytes
in MinIO first, which is right for real uploads and fatal for an evaluation
harness: CI runs Postgres and nothing else, so a harness that needed S3 could
never run in CI — and a quality gate that cannot run is a document, not a
gate. This writes chunks straight to the database using the same parser and
chunker the real pipeline uses, so what is measured is the real retrieval
surface over a known corpus.

The one thing not stubbed is embeddings. Fake vectors would make dense
retrieval scores fiction. When no embedding model is reachable the corpus is
still built and indexed for the lexical arm, and the harness says so and
declines to report dense metrics.
"""

from __future__ import annotations

import hashlib
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.models.knowledge import (
    KBChunk,
    KBCollection,
    KBCollectionGrant,
    KBDocument,
    KBDocumentVersion,
    KBVersionStatus,
)
from app.services.kb_chunking import chunk_blocks
from app.services.kb_parsing import parse

CORPUS_DIR = Path(__file__).parent / "corpus"

#: Marks collections this module owns, so rebuilding never touches a
#: collection an operator created by hand.
EVAL_PREFIX = "[eval] "


@dataclass(frozen=True)
class CorpusDoc:
    filename: str
    title: str
    collection: str


@dataclass(frozen=True)
class CorpusCollection:
    name: str
    roles: tuple[str, ...]


#: Grants are part of the fixture, not decoration. The treasury collection is
#: withheld from `agent` precisely so the access-control cases in the golden
#: set have something real to fail against.
COLLECTIONS: tuple[CorpusCollection, ...] = (
    CorpusCollection("Disputes & chargebacks", ("agent", "supervisor", "admin")),
    CorpusCollection("Compliance policies", ("agent", "supervisor", "admin")),
    CorpusCollection("Treasury runbooks", ("supervisor", "admin")),
)

DOCUMENTS: tuple[CorpusDoc, ...] = (
    CorpusDoc("chargeback-policy.md", "Chargeback Handling Policy", "Disputes & chargebacks"),
    CorpusDoc("kyc-refresh.md", "KYC Refresh Procedure", "Compliance policies"),
    CorpusDoc("monitoring-thresholds.md", "Transaction Monitoring Thresholds", "Compliance policies"),
    CorpusDoc("eod-settlement.md", "End-of-Day Settlement Runbook", "Treasury runbooks"),
)

EmbedFn = Callable[[list[str]], Awaitable[list[list[float]]]]


@dataclass
class BuildReport:
    collections: int = 0
    documents: int = 0
    chunks: int = 0
    embedded: int = 0
    dense_available: bool = False


async def teardown(db: AsyncSession) -> None:
    """Remove everything this module created. Cascades to chunks."""
    await db.execute(
        delete(KBCollection).where(KBCollection.name.startswith(EVAL_PREFIX))
    )
    await db.commit()


async def build(db: AsyncSession, *, embed: EmbedFn | None) -> BuildReport:
    """Create the eval corpus, replacing any previous build.

    Idempotent by demolition: the previous eval collections are dropped first,
    so a rebuild after editing a corpus file cannot leave stale chunks behind
    that would answer questions from a document that no longer says that.
    """
    await teardown(db)
    report = BuildReport(dense_available=embed is not None)

    collections: dict[str, KBCollection] = {}
    for spec in COLLECTIONS:
        collection = KBCollection(
            id=uuid.uuid4(),
            name=f"{EVAL_PREFIX}{spec.name}",
            description="Fixture for the knowledge-base golden set.",
            is_active=True,
        )
        db.add(collection)
        await db.flush()
        for role_name in spec.roles:
            db.add(
                KBCollectionGrant(
                    id=uuid.uuid4(), collection_id=collection.id, role_name=role_name
                )
            )
        collections[spec.name] = collection
        report.collections += 1
    await db.flush()

    for spec in DOCUMENTS:
        path = CORPUS_DIR / spec.filename
        if not path.exists():
            raise SystemExit(f"Corpus file missing: {path}")
        data = path.read_bytes()
        collection = collections[spec.collection]

        document = KBDocument(
            id=uuid.uuid4(),
            collection_id=collection.id,
            title=spec.title,
            original_filename=spec.filename,
            content_type="text/markdown",
        )
        db.add(document)
        await db.flush()

        version = KBDocumentVersion(
            id=uuid.uuid4(),
            document_id=document.id,
            version_no=1,
            # No object is stored, but the column is NOT NULL and unique. The
            # key is marked so nothing mistakes it for a real S3 object.
            s3_key=f"eval://{spec.filename}/{uuid.uuid4().hex}",
            s3_bucket="eval-fixture",
            size_bytes=len(data),
            checksum_sha256=hashlib.sha256(data).hexdigest(),
            status=KBVersionStatus.PROCESSING.value,
            embedding_model=settings.KB_EMBEDDING_MODEL if embed else None,
        )
        db.add(version)
        await db.flush()

        # The real parser and the real chunker — the point is to measure
        # retrieval over passages shaped exactly as production shapes them.
        parsed = parse(data, "md", spec.filename)
        chunks = chunk_blocks(
            parsed.blocks,
            max_chars=settings.KB_CHUNK_CHARS,
            overlap_chars=settings.KB_CHUNK_OVERLAP_CHARS,
        )

        rows: list[KBChunk] = []
        for chunk in chunks:
            rows.append(
                KBChunk(
                    id=uuid.uuid4(),
                    version_id=version.id,
                    document_id=document.id,
                    collection_id=collection.id,
                    ordinal=chunk.ordinal,
                    heading_path=chunk.heading_path,
                    content=chunk.content,
                    char_count=chunk.char_count,
                    page_from=chunk.page_from,
                    page_to=chunk.page_to,
                )
            )
        db.add_all(rows)
        await db.flush()
        report.chunks += len(rows)

        if embed is not None:
            batch = 16
            for start in range(0, len(chunks), batch):
                window = chunks[start : start + batch]
                vectors = await embed([c.embedding_text() for c in window])
                for row, vector in zip(rows[start : start + len(window)], vectors, strict=True):
                    row.embedding = vector
                report.embedded += len(window)

        version.chunk_count = len(rows)
        version.embedded_count = report.embedded if embed else 0
        version.page_count = parsed.page_count

        # A version is only READY when it is genuinely retrievable. Without
        # embeddings the dense arm cannot see it, but the lexical arm can — and
        # the retrieval predicate requires `embedding IS NOT NULL`, so a
        # lexical-only corpus must be marked honestly rather than pretending.
        version.status = KBVersionStatus.READY.value
        document.active_version_id = version.id
        report.documents += 1

    await db.commit()
    return report


async def is_built(db: AsyncSession) -> bool:
    count = (
        await db.execute(
            select(KBCollection.id).where(KBCollection.name.startswith(EVAL_PREFIX))
        )
    ).scalars().all()
    return len(count) == len(COLLECTIONS)
