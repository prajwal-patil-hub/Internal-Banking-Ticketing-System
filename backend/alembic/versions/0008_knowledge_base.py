"""Knowledge base (RAG): collections, grants, documents, versions, chunks, query log.

Enables the `vector` extension and creates the six tables described in
`app/models/knowledge.py`.

Two things here will bite an operator if they are not stated plainly:

**`CREATE EXTENSION vector` needs the extension present in the server image.**
Stock `postgres:15`/`postgres:16` do not ship it and this migration will fail
on them with "could not open extension control file". The compose files and CI
therefore pin `pgvector/pgvector:pg15` / `pg16`. It also needs superuser (or a
role with CREATE on the database) the first time; on managed Postgres the
extension usually has to be allow-listed by the provider first.

**The vector dimension is baked into the DDL.** `Vector(768)` matches
`settings.KB_EMBEDDING_DIM` and the default `nomic-embed-text` model. Changing
the embedding model to one with a different width is a migration plus a full
re-index, not a config edit — `kb_document_versions.embedding_model` records
which model produced each version so the mismatch is detectable.

The HNSW index is created with `vector_cosine_ops` because retrieval compares
with cosine distance. Building it on an empty table is instant; it is the
re-index of a populated table that is slow, which is the reason to create it
now rather than "later, when we have data".

Revision ID: 0008_knowledge_base
Revises: 0007_comment_attachments
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision: str = "0008_knowledge_base"
down_revision: Union[str, None] = "0007_comment_attachments"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

#: Must equal settings.KB_EMBEDDING_DIM. Hard-coded rather than imported so the
#: migration describes the schema it actually created, even if config changes.
EMBEDDING_DIM = 768


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "kb_collections",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    op.create_table(
        "kb_collection_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role_name", sa.String(50), nullable=False),
        sa.Column(
            "granted_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("collection_id", "role_name", name="uq_kb_grant_collection_role"),
    )
    op.create_index("ix_kb_collection_grants_collection_id", "kb_collection_grants", ["collection_id"])
    op.create_index("ix_kb_grants_role_name", "kb_collection_grants", ["role_name"])

    # Documents and versions reference each other (active_version_id ↔ document_id).
    # The active-version FK is added after both tables exist.
    op.create_table(
        "kb_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(100), nullable=False),
        sa.Column("active_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column(
            "uploaded_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_kb_documents_collection_id", "kb_documents", ["collection_id"])

    op.create_table(
        "kb_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("version_no", sa.Integer(), nullable=False),
        sa.Column("s3_key", sa.String(500), nullable=False, unique=True),
        sa.Column("s3_bucket", sa.String(100), nullable=False),
        sa.Column("size_bytes", sa.BigInteger(), nullable=False),
        sa.Column("checksum_sha256", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedded_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("embedding_model", sa.String(100), nullable=True),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_by_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("document_id", "version_no", name="uq_kb_version_doc_no"),
    )
    op.create_index("ix_kb_versions_document_id", "kb_document_versions", ["document_id"])
    op.create_index(
        "ix_kb_document_versions_checksum_sha256", "kb_document_versions", ["checksum_sha256"]
    )

    op.create_foreign_key(
        "fk_kb_documents_active_version",
        "kb_documents",
        "kb_document_versions",
        ["active_version_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "kb_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "version_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_document_versions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_documents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Denormalised on purpose — this is the column the access predicate
        # filters on, so it must not depend on a join surviving a refactor.
        sa.Column(
            "collection_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("kb_collections.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("heading_path", sa.String(500), nullable=True),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("char_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("page_from", sa.Integer(), nullable=True),
        sa.Column("page_to", sa.Integer(), nullable=True),
        sa.Column("embedding", Vector(EMBEDDING_DIM), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.UniqueConstraint("version_id", "ordinal", name="uq_kb_chunk_version_ordinal"),
    )
    op.create_index("ix_kb_chunks_version_id", "kb_chunks", ["version_id"])
    op.create_index("ix_kb_chunks_collection_id", "kb_chunks", ["collection_id"])

    # Dense retrieval. m/ef_construction are pgvector's documented defaults;
    # they are stated explicitly so a later tuning change is a visible diff.
    op.execute(
        "CREATE INDEX ix_kb_chunks_embedding_hnsw ON kb_chunks "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )

    # Lexical retrieval. Expression index rather than a stored tsvector column:
    # the query uses the identical expression, so one definition serves both.
    op.execute(
        "CREATE INDEX ix_kb_chunks_content_fts ON kb_chunks "
        "USING gin (to_tsvector('english', content))"
    )

    op.create_table(
        "kb_query_logs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("retrieved_chunk_ids", postgresql.JSONB(), nullable=True),
        sa.Column("cited_chunk_ids", postgresql.JSONB(), nullable=True),
        sa.Column("rejected_citations", postgresql.JSONB(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("confidence_band", sa.String(20), nullable=True),
        sa.Column("abstained", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("abstain_reason", sa.String(100), nullable=True),
        sa.Column("model_id", sa.String(100), nullable=True),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("retrieval_ms", sa.Integer(), nullable=True),
        sa.Column("total_ms", sa.Integer(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )
    op.create_index("ix_kb_query_logs_user_id", "kb_query_logs", ["user_id"])
    op.create_index("ix_kb_query_logs_created_at", "kb_query_logs", ["created_at"])


def downgrade() -> None:
    op.drop_table("kb_query_logs")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_content_fts")
    op.execute("DROP INDEX IF EXISTS ix_kb_chunks_embedding_hnsw")
    op.drop_table("kb_chunks")
    op.drop_constraint("fk_kb_documents_active_version", "kb_documents", type_="foreignkey")
    op.drop_table("kb_document_versions")
    op.drop_table("kb_documents")
    op.drop_table("kb_collection_grants")
    op.drop_table("kb_collections")
    # The `vector` extension is deliberately NOT dropped: another schema in the
    # same database may be using it, and dropping it would cascade their columns.
