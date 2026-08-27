"""The access boundary, executed against a real database.

Every other test of `accessible_collections` inspects the *compiled* SQL. That
proves the predicate is in the statement; it does not prove the statement
returns the right rows. The difference matters here more than anywhere else in
the product: this is the query that decides whether one department's policy
manual can be read out to another department's agent, and a predicate can be
present and still be wrong (joined the wrong way, comparing the wrong column,
defeated by a NULL).

So these insert real collections, grants, documents, versions and chunks —
with real 768-dimensional vectors — and assert on rows that actually come
back. They need Postgres with pgvector and are skipped without DATABASE_URL,
exactly like the other database-backed tests.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select

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
from app.services.kb_retrieval_service import accessible_collections

pytestmark = pytest.mark.asyncio

DIM = 768


async def _role(db, name: str) -> Role:
    role = (await db.execute(select(Role).where(Role.name == name))).scalar_one_or_none()
    if role is None:
        role = Role(id=uuid.uuid4(), name=name, description=name)
        db.add(role)
        await db.flush()
    return role


async def _user(db, role_name: str, *, super_admin: bool = False) -> User:
    role = await _role(db, role_name)
    user = User(
        id=uuid.uuid4(),
        email=f"{role_name}-{uuid.uuid4().hex[:8]}@bank.com",
        full_name=role_name,
        password_hash="x",
        role_id=role.id,
        is_active=True,
        mfa_enabled=False,
        failed_login_count=0,
        is_super_admin=super_admin,
    )
    db.add(user)
    await db.flush()
    user.role = role
    return user


async def _collection(db, name: str, *, roles: list[str], is_active: bool = True):
    collection = KBCollection(
        id=uuid.uuid4(), name=f"{name}-{uuid.uuid4().hex[:6]}", is_active=is_active
    )
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


async def _document_with_chunk(
    db,
    collection: KBCollection,
    text: str,
    *,
    vector: list[float] | None = None,
    activate: bool = True,
    status: str = KBVersionStatus.READY.value,
):
    """A document with one indexed passage, wired exactly as ingestion wires it."""
    document = KBDocument(
        id=uuid.uuid4(),
        collection_id=collection.id,
        title=text[:40],
        original_filename="doc.md",
        content_type="text/markdown",
    )
    db.add(document)
    await db.flush()

    version = KBDocumentVersion(
        id=uuid.uuid4(),
        document_id=document.id,
        version_no=1,
        s3_key=f"kb/{collection.id}/{uuid.uuid4().hex}.md",
        s3_bucket="test",
        size_bytes=len(text),
        checksum_sha256="a" * 64,
        status=status,
        chunk_count=1,
        embedded_count=1,
    )
    db.add(version)
    await db.flush()

    db.add(
        KBChunk(
            id=uuid.uuid4(),
            version_id=version.id,
            document_id=document.id,
            collection_id=collection.id,
            ordinal=0,
            content=text,
            char_count=len(text),
            embedding=vector or [0.01] * DIM,
        )
    )
    if activate:
        document.active_version_id = version.id
    await db.flush()
    return document, version


async def _accessible_ids(db, user) -> set[uuid.UUID]:
    rows = (await db.execute(accessible_collections(user))).scalars().all()
    return set(rows)


# ---------------------------------------------------------------------------
# The boundary itself
# ---------------------------------------------------------------------------

async def test_agent_sees_only_collections_granted_to_their_role(db_session) -> None:
    db = db_session
    granted = await _collection(db, "granted", roles=["agent"])
    other = await _collection(db, "supervisors-only", roles=["supervisor"])
    ungranted = await _collection(db, "nobody", roles=[])

    agent = await _user(db, "agent")
    visible = await _accessible_ids(db, agent)

    assert granted.id in visible
    assert other.id not in visible, "agent reached a supervisor-only collection"
    assert ungranted.id not in visible, "agent reached a collection with no grants"


async def test_a_grant_to_another_role_does_not_leak(db_session) -> None:
    db = db_session
    collection = await _collection(db, "treasury", roles=["supervisor", "admin"])

    agent = await _user(db, "agent")
    supervisor = await _user(db, "supervisor")

    assert collection.id not in await _accessible_ids(db, agent)
    assert collection.id in await _accessible_ids(db, supervisor)


async def test_inactive_collections_are_invisible_even_when_granted(db_session) -> None:
    db = db_session
    collection = await _collection(db, "retired", roles=["agent"], is_active=False)
    agent = await _user(db, "agent")
    assert collection.id not in await _accessible_ids(db, agent)


async def test_super_admin_sees_every_active_collection(db_session) -> None:
    db = db_session
    a = await _collection(db, "a", roles=[])
    b = await _collection(db, "b", roles=["supervisor"])
    inactive = await _collection(db, "c", roles=["admin"], is_active=False)

    boss = await _user(db, "admin", super_admin=True)
    visible = await _accessible_ids(db, boss)

    assert {a.id, b.id} <= visible
    assert inactive.id not in visible, "super admin saw an inactive collection"


async def test_branch_user_super_admin_is_still_filtered_by_grants(db_session) -> None:
    """The escalation the review found: `is_read_only` covers only `auditor`,
    so a branch user with the flag skipped the grant join entirely."""
    db = db_session
    secret = await _collection(db, "compliance", roles=["admin"])
    raiser = await _user(db, "branch_user", super_admin=True)
    assert secret.id not in await _accessible_ids(db, raiser)


async def test_auditor_super_admin_is_still_filtered_by_grants(db_session) -> None:
    db = db_session
    secret = await _collection(db, "compliance", roles=["admin"])
    auditor = await _user(db, "auditor", super_admin=True)
    assert secret.id not in await _accessible_ids(db, auditor)


# ---------------------------------------------------------------------------
# The same boundary, applied to the chunks retrieval actually reads
# ---------------------------------------------------------------------------

async def _retrievable_chunks(db, user) -> list[str]:
    """Run the real retrieval predicate and return the passage text."""
    from app.services.kb_retrieval_service import _retrievable

    stmt = (
        select(KBChunk.content)
        .join(KBDocument, KBChunk.document_id == KBDocument.id)
        .where(*_retrievable(user))
    )
    return list((await db.execute(stmt)).scalars().all())


async def test_passages_from_an_ungranted_collection_are_never_selected(db_session) -> None:
    """The property the whole design rests on: a passage the caller may not
    read is not filtered out of the answer, it is never retrieved at all — so
    it cannot reach the prompt, and prompt injection cannot surface it."""
    db = db_session
    mine = await _collection(db, "disputes", roles=["agent"])
    theirs = await _collection(db, "board-papers", roles=["admin"])

    await _document_with_chunk(db, mine, "Chargebacks must be raised within 45 days.")
    await _document_with_chunk(db, theirs, "Project Falcon acquisition price is 4.2bn.")

    agent = await _user(db, "agent")
    texts = await _retrievable_chunks(db, agent)

    assert any("45 days" in t for t in texts)
    assert not any("Falcon" in t for t in texts), "restricted passage was retrievable"


async def test_only_the_active_version_is_retrievable(db_session) -> None:
    """A failed re-index must not serve half a policy."""
    db = db_session
    collection = await _collection(db, "policies", roles=["agent"])
    await _document_with_chunk(db, collection, "Active text.", activate=True)
    await _document_with_chunk(
        db,
        collection,
        "Orphaned text from a version that never activated.",
        activate=False,
        status=KBVersionStatus.FAILED.value,
    )

    agent = await _user(db, "agent")
    texts = await _retrievable_chunks(db, agent)

    assert any("Active text" in t for t in texts)
    assert not any("Orphaned" in t for t in texts)


async def test_chunks_without_an_embedding_are_not_retrievable(db_session) -> None:
    """Ingestion inserts chunks before embedding them; a crash in between must
    not leave un-vectorised passages in the searchable set."""
    db = db_session
    collection = await _collection(db, "policies", roles=["agent"])
    document, version = await _document_with_chunk(db, collection, "Embedded text.")
    db.add(
        KBChunk(
            id=uuid.uuid4(),
            version_id=version.id,
            document_id=document.id,
            collection_id=collection.id,
            ordinal=1,
            content="Not yet embedded.",
            char_count=17,
            embedding=None,
        )
    )
    await db.flush()

    agent = await _user(db, "agent")
    texts = await _retrievable_chunks(db, agent)
    assert any("Embedded text" in t for t in texts)
    assert not any("Not yet embedded" in t for t in texts)


# ---------------------------------------------------------------------------
# pgvector and full-text actually work, not just compile
# ---------------------------------------------------------------------------

async def test_cosine_distance_orders_by_similarity(db_session) -> None:
    db = db_session
    collection = await _collection(db, "vectors", roles=["agent"])

    near = [0.0] * DIM
    near[0] = 1.0
    far = [0.0] * DIM
    far[1] = 1.0

    await _document_with_chunk(db, collection, "near passage", vector=near)
    await _document_with_chunk(db, collection, "far passage", vector=far)

    query = [0.0] * DIM
    query[0] = 1.0

    agent = await _user(db, "agent")
    from app.services.kb_retrieval_service import _retrievable

    distance = KBChunk.embedding.cosine_distance(query)
    rows = (
        await db.execute(
            select(KBChunk.content, distance)
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .where(*_retrievable(agent))
            .order_by(distance)
        )
    ).all()

    assert rows[0][0] == "near passage"
    assert rows[0][1] < rows[-1][1]


async def test_full_text_arm_matches_on_words(db_session) -> None:
    db = db_session
    from sqlalchemy import func

    from app.services.kb_retrieval_service import _retrievable

    collection = await _collection(db, "lexical", roles=["agent"])
    await _document_with_chunk(db, collection, "Chargeback timelines for disputed transactions.")
    await _document_with_chunk(db, collection, "Cheque truncation settlement windows.")

    agent = await _user(db, "agent")
    tsvector = func.to_tsvector("english", KBChunk.content)
    tsquery = func.plainto_tsquery("english", "chargeback timelines")

    rows = (
        await db.execute(
            select(KBChunk.content)
            .join(KBDocument, KBChunk.document_id == KBDocument.id)
            .where(*_retrievable(agent), tsvector.op("@@")(tsquery))
        )
    ).scalars().all()

    assert any("Chargeback" in r for r in rows)
    assert not any("truncation" in r for r in rows)


async def test_unique_constraint_rejects_duplicate_ordinals(db_session) -> None:
    """(version_id, ordinal) is what makes a rebuild safe; if it were missing,
    a re-index could silently double every passage."""
    from sqlalchemy.exc import IntegrityError

    db = db_session
    collection = await _collection(db, "dupes", roles=["agent"])
    document, version = await _document_with_chunk(db, collection, "First.")

    # Inside a savepoint: a failed flush poisons the enclosing transaction, and
    # the fixture's rollback then warns about a connection it no longer owns.
    async with db.begin_nested():
        db.add(
            KBChunk(
                id=uuid.uuid4(),
                version_id=version.id,
                document_id=document.id,
                collection_id=collection.id,
                ordinal=0,
                content="Duplicate ordinal.",
                char_count=18,
                embedding=[0.01] * DIM,
            )
        )
        with pytest.raises(IntegrityError):
            await db.flush()
