"""Ingestion end to end, against a real database.

The unit tests cover parsing, chunking and the activation gate in isolation
with a mocked session. This runs the whole path — upload bytes, parse, chunk,
insert, embed, activate, then retrieve — through real SQL, real pgvector
columns and the real unique constraints.

Object storage and the embedding model are the only stubs, and they are stubbed
rather than skipped for a reason: MinIO and Ollama are separate services whose
own failures are already covered elsewhere, while the thing that has never been
exercised is whether the pipeline's *database* work is correct. Everything
between the bytes and the retrievable passage is the real implementation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import func, select

from app.core.config import settings
from app.models.knowledge import (
    KBChunk,
    KBCollection,
    KBCollectionGrant,
    KBDocument,
    KBDocumentVersion,
    KBVersionStatus,
)
from app.models.role import Role
from app.models.user import User
from app.services import llm_client
from app.services.kb_ingestion_service import KBIngestionService

pytestmark = pytest.mark.asyncio

POLICY = b"""# Chargeback Policy

## 3. Chargebacks

### 3.2 Timelines

A service dispute must be raised within 45 days of the transaction date.
Late claims are rejected automatically by the scheme.

### 3.3 Evidence

Attach the signed dispute form and the statement extract.
"""


class _MemoryStorage:
    """Object storage that keeps bytes in a dict.

    Mirrors `StorageService`'s contract exactly — `upload` returns an object
    carrying the key, bucket, size and checksum — so the service under test
    cannot tell the difference.
    """

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    async def upload(self, key: str, data: bytes, content_type: str):
        import hashlib
        from dataclasses import dataclass

        @dataclass
        class Stored:
            key: str
            bucket: str
            size_bytes: int
            checksum_sha256: str

        self.objects[key] = data
        return Stored(key, "test-bucket", len(data), hashlib.sha256(data).hexdigest())

    async def download(self, key: str) -> bytes:
        return self.objects[key]

    async def delete(self, key: str) -> None:
        self.objects.pop(key, None)


def _deterministic_vector(text: str) -> list[float]:
    """A stable pseudo-embedding: same text, same vector.

    Not semantically meaningful, and not pretending to be — its only job is to
    be a real 768-float value that pgvector will store, index and compare.
    """
    vector = [0.0] * settings.KB_EMBEDDING_DIM
    for i, ch in enumerate(text[:512]):
        vector[(ord(ch) + i) % settings.KB_EMBEDDING_DIM] += 1.0
    norm = sum(v * v for v in vector) ** 0.5 or 1.0
    return [v / norm for v in vector]


@pytest.fixture
def stub_embeddings(monkeypatch):
    async def fake_embed(texts: list[str]) -> list[list[float]]:
        return [_deterministic_vector(t) for t in texts]

    monkeypatch.setattr(llm_client, "embed", fake_embed)
    return fake_embed


async def _admin(db) -> User:
    role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one_or_none()
    if role is None:
        role = Role(id=uuid.uuid4(), name="admin", description="admin")
        db.add(role)
        await db.flush()
    user = User(
        id=uuid.uuid4(),
        email=f"admin-{uuid.uuid4().hex[:8]}@bank.com",
        full_name="Admin",
        password_hash="x",
        role_id=role.id,
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
    )
    db.add(user)
    await db.flush()
    user.role = role
    return user


async def _collection(db, *, roles: list[str]) -> KBCollection:
    collection = KBCollection(id=uuid.uuid4(), name=f"c-{uuid.uuid4().hex[:8]}", is_active=True)
    db.add(collection)
    await db.flush()
    for role_name in roles:
        db.add(
            KBCollectionGrant(
                id=uuid.uuid4(), collection_id=collection.id, role_name=role_name
            )
        )
    await db.flush()
    return collection


def _service(db) -> KBIngestionService:
    service = KBIngestionService(db)
    service.storage = _MemoryStorage()  # type: ignore[assignment]
    return service


# ---------------------------------------------------------------------------
# The whole path
# ---------------------------------------------------------------------------

async def test_a_document_becomes_retrievable_passages(db_session, stub_embeddings) -> None:
    db = db_session
    admin = await _admin(db)
    collection = await _collection(db, roles=["agent"])
    service = _service(db)

    document, version, duplicate = await service.ingest(
        collection=collection,
        filename="chargeback-policy.md",
        content_type="text/markdown",
        data=POLICY,
        user=admin,
        title="Chargeback Policy",
    )

    assert duplicate is False
    assert version.status == KBVersionStatus.READY.value
    assert version.chunk_count == version.embedded_count > 0
    assert document.active_version_id == version.id

    chunks = (
        await db.execute(select(KBChunk).where(KBChunk.version_id == version.id))
    ).scalars().all()
    assert len(chunks) == version.chunk_count
    # Every chunk carries a vector, the denormalised security key, and the
    # heading path that makes a passage make sense on its own.
    assert all(c.embedding is not None for c in chunks)
    assert all(c.collection_id == collection.id for c in chunks)
    assert any(c.heading_path and "3.2 Timelines" in c.heading_path for c in chunks)
    assert any("45 days" in c.content for c in chunks)


async def test_reuploading_identical_bytes_does_not_duplicate_the_index(
    db_session, stub_embeddings
) -> None:
    db = db_session
    admin = await _admin(db)
    collection = await _collection(db, roles=["agent"])
    service = _service(db)

    document, version, _ = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=POLICY, user=admin,
    )
    before = (
        await db.execute(select(func.count(KBChunk.id)).where(KBChunk.document_id == document.id))
    ).scalar_one()

    _doc2, version2, duplicate = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=POLICY, user=admin, document=document,
    )
    after = (
        await db.execute(select(func.count(KBChunk.id)).where(KBChunk.document_id == document.id))
    ).scalar_one()

    assert duplicate is True
    assert version2.id == version.id
    assert after == before, "re-upload duplicated the vectors"


async def test_a_changed_document_supersedes_the_previous_version(
    db_session, stub_embeddings
) -> None:
    """The new version serves, and the old one stops being retrievable —
    without ever leaving a window where neither does."""
    db = db_session
    admin = await _admin(db)
    collection = await _collection(db, roles=["agent"])
    service = _service(db)

    document, v1, _ = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=POLICY, user=admin,
    )
    updated = POLICY.replace(b"45 days", b"60 days")
    _doc, v2, duplicate = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=updated, user=admin, document=document,
    )

    assert duplicate is False
    assert v2.id != v1.id
    assert v2.version_no == v1.version_no + 1
    await db.refresh(document)
    assert document.active_version_id == v2.id

    live = (
        await db.execute(
            select(KBChunk.content).where(KBChunk.version_id == document.active_version_id)
        )
    ).scalars().all()
    assert any("60 days" in c for c in live)
    assert not any("45 days" in c for c in live)


async def test_an_embedding_failure_leaves_the_previous_version_serving(
    committing_session, stub_embeddings, monkeypatch
) -> None:
    """The invariant the two-phase design exists for, proven against real rows.

    Uses `committing_session` rather than `db_session`: the service rolls back
    on failure, and that rollback would unwind the shared fixture's own
    transaction — taking this test's fixtures with it and proving nothing.
    """
    db = committing_session
    admin = await _admin(db)
    collection = await _collection(db, roles=["agent"])
    service = _service(db)

    document, v1, _ = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=POLICY, user=admin,
    )

    async def boom(_texts):
        raise llm_client.EmbeddingError("ollama is down")

    monkeypatch.setattr(llm_client, "embed", boom)

    with pytest.raises(llm_client.EmbeddingError):
        await service.ingest(
            collection=collection, filename="p.md", content_type="text/markdown",
            data=POLICY.replace(b"45 days", b"90 days"), user=admin, document=document,
        )

    await db.refresh(document)
    assert document.active_version_id == v1.id, "a failed re-index took the document down"

    versions = (
        await db.execute(
            select(KBDocumentVersion).where(KBDocumentVersion.document_id == document.id)
        )
    ).scalars().all()
    failed = [v for v in versions if v.status == KBVersionStatus.FAILED.value]
    assert failed and "ollama is down" in (failed[0].error_message or "")

    # The old answer is still being served.
    live = (
        await db.execute(
            select(KBChunk.content).where(KBChunk.version_id == document.active_version_id)
        )
    ).scalars().all()
    assert any("45 days" in c for c in live)
    assert not any("90 days" in c for c in live)


async def test_deleting_a_document_removes_its_passages(db_session, stub_embeddings) -> None:
    db = db_session
    admin = await _admin(db)
    collection = await _collection(db, roles=["agent"])
    service = _service(db)

    document, _v, _ = await service.ingest(
        collection=collection, filename="p.md", content_type="text/markdown",
        data=POLICY, user=admin,
    )
    document_id = document.id

    await service.delete_document(document)

    remaining = (
        await db.execute(select(func.count(KBChunk.id)).where(KBChunk.document_id == document_id))
    ).scalar_one()
    assert remaining == 0
    assert (await db.get(KBDocument, document_id)) is None


async def test_ingested_passages_respect_the_access_boundary(
    db_session, stub_embeddings
) -> None:
    """Ingestion stamps the security key correctly, not just plausibly."""
    db = db_session
    from app.services.kb_retrieval_service import _retrievable

    admin = await _admin(db)
    restricted = await _collection(db, roles=["admin"])
    service = _service(db)
    await service.ingest(
        collection=restricted, filename="board.md", content_type="text/markdown",
        data=b"# Board\n\nProject Falcon price is 4.2bn.\n", user=admin,
    )

    agent_role = (
        await db.execute(select(Role).where(Role.name == "agent"))
    ).scalar_one_or_none()
    if agent_role is None:
        agent_role = Role(id=uuid.uuid4(), name="agent", description="agent")
        db.add(agent_role)
        await db.flush()
    agent = User(
        id=uuid.uuid4(), email=f"a-{uuid.uuid4().hex[:8]}@bank.com", full_name="A",
        password_hash="x", role_id=agent_role.id, is_active=True, mfa_enabled=False,
        failed_login_count=0,
    )
    db.add(agent)
    await db.flush()
    agent.role = agent_role

    texts = (
        await db.execute(
            select(KBChunk.content)
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .where(*_retrievable(agent))
        )
    ).scalars().all()
    assert not any("Falcon" in t for t in texts)
