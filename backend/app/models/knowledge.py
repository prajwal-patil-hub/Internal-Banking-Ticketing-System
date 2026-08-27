"""Knowledge-base (RAG) models.

Six tables, and the shape of them is mostly driven by one requirement: a
retrieval query must be able to enforce access control **in SQL, before any
text reaches the model**. An access check applied to the model's *answer* is a
check that has already leaked — the passage was in the prompt by then.

That requirement is why `kb_chunks` carries a denormalised `collection_id`.
It is redundant (chunk → version → document → collection would get you there)
but the redundancy is the point: the security predicate becomes a single
`WHERE kb_chunks.collection_id IN (...)` that cannot be dropped by someone
refactoring a join, and it stays correct when the retrieval query is rewritten
for performance. A three-hop join is exactly the kind of thing that gets
flattened into a subquery one afternoon and silently loses its filter.

Access is granted per *role*, not per user. Five roles exist and they are
few and stable; per-user grants would need their own revocation story and an
admin screen nobody asked for. `kb_collection_grants` is therefore
(collection, role_name) with a uniqueness constraint.

Versioning exists for one reason: a document must never be *partially*
retrievable. Chunks are written against a version; the version flips to
`READY` only once every one of its chunks has an embedding; and retrieval
reads through `kb_documents.active_version_id`. A failed re-index leaves the
previous version serving traffic instead of half-indexing the new one.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.config import settings
from app.db.base import Base, TimestampMixin, UUIDPKMixin


class KBVersionStatus(str, enum.Enum):
    """Lifecycle of one uploaded revision of a document.

    Only `READY` is retrievable. `PROCESSING` exists so a long ingestion is
    visible in the admin UI rather than looking like a hung upload.
    """

    PENDING = "pending"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"


class KBCollection(UUIDPKMixin, TimestampMixin, Base):
    """A named group of documents that access is granted against.

    Grants hang off the collection rather than the document because that is
    the unit an administrator actually reasons about ("Compliance policies",
    "Treasury runbooks") — per-document ACLs drift the moment someone uploads
    a file into the wrong place.
    """

    __tablename__ = "kb_collections"

    name: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(500), nullable=True)

    #: Soft switch so a collection can be taken out of retrieval without
    #: deleting its documents (and their audit history).
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    grants: Mapped[list[KBCollectionGrant]] = relationship(
        back_populates="collection",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class KBCollectionGrant(UUIDPKMixin, TimestampMixin, Base):
    """"Role R may read collection C."

    Absence of a row is denial. There is no "public" collection flag and no
    implicit grant: a new collection is readable by nobody until an admin says
    otherwise, which is the safe default for bank documents.
    """

    __tablename__ = "kb_collection_grants"
    __table_args__ = (
        UniqueConstraint("collection_id", "role_name", name="uq_kb_grant_collection_role"),
        Index("ix_kb_grants_role_name", "role_name"),
    )

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: Matches `roles.name`. Stored as text rather than an FK because the
    #: retrieval predicate compares against `user.role.name`, which is already
    #: loaded on every request — an FK would force a join into the hot path.
    role_name: Mapped[str] = mapped_column(String(50), nullable=False)

    granted_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    collection: Mapped[KBCollection] = relationship(back_populates="grants")


class KBDocument(UUIDPKMixin, TimestampMixin, Base):
    """A logical document. Its retrievable content lives on a version."""

    __tablename__ = "kb_documents"
    __table_args__ = (Index("ix_kb_documents_collection_id", "collection_id"),)

    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)

    #: The version currently serving retrieval. NULL until the first ingestion
    #: succeeds, which is what keeps a never-indexed document invisible.
    #:
    #: `use_alter` breaks the circular FK between documents and versions at
    #: DDL time — without it the two CREATE TABLEs cannot be ordered.
    active_version_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey(
            "kb_document_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_kb_documents_active_version",
        ),
        nullable=True,
    )

    uploaded_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    versions: Mapped[list[KBDocumentVersion]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        lazy="selectin",
        foreign_keys="KBDocumentVersion.document_id",
    )


class KBDocumentVersion(UUIDPKMixin, TimestampMixin, Base):
    """One uploaded revision: the stored bytes plus its ingestion state."""

    __tablename__ = "kb_document_versions"
    __table_args__ = (
        UniqueConstraint("document_id", "version_no", name="uq_kb_version_doc_no"),
        Index("ix_kb_versions_document_id", "document_id"),
    )

    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)

    s3_key: Mapped[str] = mapped_column(String(500), unique=True, nullable=False)
    s3_bucket: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    #: Re-uploading identical bytes is detected here and short-circuits to a
    #: pointer at the existing version rather than re-embedding the file.
    checksum_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    status: Mapped[str] = mapped_column(
        String(20), default=KBVersionStatus.PENDING.value, nullable=False
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunk_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    embedded_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    #: Which embedding model produced this version's vectors. A config change
    #: makes old vectors incomparable; recording it makes that detectable.
    embedding_model: Mapped[str | None] = mapped_column(String(100), nullable=True)

    page_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_by_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    document: Mapped[KBDocument] = relationship(
        back_populates="versions", foreign_keys=[document_id]
    )


class KBChunk(UUIDPKMixin, TimestampMixin, Base):
    """A retrievable passage.

    `collection_id` is denormalised deliberately — see the module docstring.
    It is the column the access predicate filters on.
    """

    __tablename__ = "kb_chunks"
    __table_args__ = (
        Index("ix_kb_chunks_version_id", "version_id"),
        Index("ix_kb_chunks_collection_id", "collection_id"),
        UniqueConstraint("version_id", "ordinal", name="uq_kb_chunk_version_ordinal"),
    )

    version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_document_versions.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: Denormalised security key. Never derive access from a join.
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("kb_collections.id", ondelete="CASCADE"),
        nullable=False,
    )

    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)

    #: "3. Chargebacks > 3.2 Timelines" — carried into the embedded text so a
    #: passage retrieved alone still knows where it sits in the document.
    heading_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    char_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    page_from: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_to: Mapped[int | None] = mapped_column(Integer, nullable=True)

    #: Dimension is fixed at migration time. `settings.KB_EMBEDDING_DIM` must
    #: agree with it; the ingestion service asserts this rather than letting
    #: pgvector reject the insert with an opaque error.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(settings.KB_EMBEDDING_DIM), nullable=True
    )


class KBQueryLog(UUIDPKMixin, TimestampMixin, Base):
    """Every knowledge-base question, and what was actually shown back.

    Kept separate from `AIInteractionLog` because the interesting fields are
    different: which passages were retrieved, which of them the answer was
    permitted to cite, and whether the system abstained. Without the retrieved
    ids on the record, a later "why did it say that?" is unanswerable.
    """

    __tablename__ = "kb_query_logs"

    user_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)

    retrieved_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    cited_chunk_ids: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    #: Citations the model produced that were NOT in the retrieved set. Should
    #: always be empty; a non-empty value is the hallucination signal and the
    #: thing the evaluation gate counts.
    rejected_citations: Mapped[list | None] = mapped_column(JSONB, nullable=True)

    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence_band: Mapped[str | None] = mapped_column(String(20), nullable=True)
    abstained: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    abstain_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)

    model_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    completion_tokens: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    retrieval_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    success: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
