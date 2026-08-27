"""Knowledge-base API: collections, grants, documents, and querying.

Two distinct permission surfaces, and they are not the same set:

* **Curation** — create a collection, grant a role access, upload or delete a
  document. Administrators and super-admins only
  (`authz.assert_can_manage_knowledge_base`). Publishing a document that every
  agent will then be answered from is a curation decision, not a working one.

* **Querying** — ask a question. Agents, supervisors and admins, matching the
  existing AI-helper guard on tickets rather than inventing a second policy.

Both guards are called inside the handler rather than declared as
`dependencies=[...]` on the router, because several of them need the resolved
`current_user` to make a super-admin decision, and a route that looks guarded
by a decorator while the real check lives elsewhere is how these drift.

Note what is *not* here: no endpoint returns a collection the caller has no
grant on, and no endpoint reports whether such a collection exists. Listing is
filtered by the same predicate retrieval uses, so "no results" and "no access"
are indistinguishable from outside — otherwise the list endpoint becomes an
oracle for the names of restricted collections.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.core import authz
from app.core.config import settings
from app.core.exceptions import NotFoundError, ValidationError
from app.core.logging import get_logger
from app.core.ratelimit import check_rate_limit
from app.models.audit import AuditAction, AuditLog
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
from app.schemas.envelope import ok
from app.services.kb_ingestion_service import KBIngestionService, validate_kb_upload
from app.services.kb_retrieval_service import (
    KBRetrievalService,
    accessible_collections,
)
from app.services.storage_service import StorageService

log = get_logger(__name__)

router = APIRouter(prefix="/kb", tags=["knowledge-base"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _audit(
    db: AsyncSession,
    *,
    action: AuditAction,
    entity_type: str,
    entity_id: str,
    user: User,
    request: Request,
    old_values: dict | None = None,
    new_values: dict | None = None,
    metadata_: dict | None = None,
) -> None:
    db.add(
        AuditLog(
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            actor_id=user.id,
            actor_email=user.email,
            actor_role=user.role.name,
            old_values=old_values,
            new_values=new_values,
            ip_address=getattr(request.state, "client_ip", None),
            user_agent=getattr(request.state, "user_agent", None),
            request_id=getattr(request.state, "request_id", None),
            metadata_=metadata_,
        )
    )


def _serialize_collection(c: KBCollection, doc_count: int = 0) -> dict:
    return {
        "id": str(c.id),
        "name": c.name,
        "description": c.description,
        "is_active": c.is_active,
        "granted_roles": sorted(g.role_name for g in c.grants),
        "document_count": doc_count,
        "created_at": c.created_at.isoformat(),
    }


def _serialize_version(v: KBDocumentVersion, is_active: bool) -> dict:
    return {
        "id": str(v.id),
        "version_no": v.version_no,
        "status": v.status,
        "error_message": v.error_message,
        "chunk_count": v.chunk_count,
        "embedded_count": v.embedded_count,
        "page_count": v.page_count,
        "size_bytes": v.size_bytes,
        "embedding_model": v.embedding_model,
        "is_active": is_active,
        "created_at": v.created_at.isoformat(),
    }


def _serialize_document(d: KBDocument) -> dict:
    versions = sorted(d.versions, key=lambda v: v.version_no, reverse=True)
    active = next((v for v in versions if v.id == d.active_version_id), None)
    return {
        "id": str(d.id),
        "collection_id": str(d.collection_id),
        "title": d.title,
        "original_filename": d.original_filename,
        "content_type": d.content_type,
        "status": active.status if active else (versions[0].status if versions else "pending"),
        "chunk_count": active.chunk_count if active else 0,
        "page_count": active.page_count if active else None,
        "size_bytes": active.size_bytes if active else (versions[0].size_bytes if versions else 0),
        "active_version_no": active.version_no if active else None,
        "version_count": len(versions),
        "versions": [_serialize_version(v, v.id == d.active_version_id) for v in versions],
        "created_at": d.created_at.isoformat(),
        "updated_at": d.updated_at.isoformat(),
    }


async def _readable_collection(
    collection_id: uuid.UUID, db: AsyncSession, user: User
) -> KBCollection:
    """Fetch a collection the caller may read, else 404.

    404 rather than 403 on purpose: a 403 confirms the collection exists, which
    tells an agent the name of a restricted collection they guessed correctly.
    """
    collection = (
        await db.execute(
            select(KBCollection).where(
                KBCollection.id == collection_id,
                KBCollection.id.in_(accessible_collections(user)),
            )
        )
    ).scalar_one_or_none()
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


async def _manageable_collection(
    collection_id: uuid.UUID, db: AsyncSession, user: User
) -> KBCollection:
    """Curation target. Managers see every collection, granted or not."""
    authz.assert_can_manage_knowledge_base(user)
    collection = await db.get(KBCollection, collection_id)
    if collection is None:
        raise NotFoundError("Collection not found.")
    return collection


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

@router.get("/collections", summary="List knowledge-base collections")
async def list_collections(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Collections the caller can read.

    Curators see everything (including inactive collections, which they need in
    order to reactivate them). Everyone else sees only what their role has been
    granted, through the same predicate retrieval uses.
    """
    if authz.can_manage_knowledge_base(current_user):
        stmt = select(KBCollection).order_by(KBCollection.name)
    else:
        authz.assert_can_query_knowledge_base(current_user)
        stmt = (
            select(KBCollection)
            .where(KBCollection.id.in_(accessible_collections(current_user)))
            .order_by(KBCollection.name)
        )

    collections = list((await db.execute(stmt)).scalars().unique().all())

    counts = dict(
        (
            await db.execute(
                select(KBDocument.collection_id, func.count(KBDocument.id)).group_by(
                    KBDocument.collection_id
                )
            )
        ).all()
    )
    return ok([_serialize_collection(c, counts.get(c.id, 0)) for c in collections])


@router.post(
    "/collections", status_code=status.HTTP_201_CREATED, summary="Create a collection"
)
async def create_collection(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    authz.assert_can_manage_knowledge_base(current_user)

    name = (payload.get("name") or "").strip()
    if not name:
        raise ValidationError("A collection name is required.")
    if len(name) > 150:
        raise ValidationError("Collection name must be 150 characters or fewer.")

    clash = (
        await db.execute(select(KBCollection).where(func.lower(KBCollection.name) == name.lower()))
    ).scalar_one_or_none()
    if clash is not None:
        raise ValidationError(f"A collection named '{name}' already exists.")

    collection = KBCollection(
        name=name,
        description=(payload.get("description") or "").strip()[:500] or None,
        created_by_id=current_user.id,
    )
    db.add(collection)
    await db.flush()

    # A new collection is readable by nobody until a grant is added. That is
    # the safe default and it is stated in the response so the UI can prompt.
    await _audit(
        db,
        action=AuditAction.CREATE,
        entity_type="kb_collection",
        entity_id=str(collection.id),
        user=current_user,
        request=request,
        new_values={"name": name},
    )
    await db.commit()
    await db.refresh(collection)
    return ok(_serialize_collection(collection))


@router.patch("/collections/{collection_id}", summary="Update a collection")
async def update_collection(
    collection_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    collection = await _manageable_collection(collection_id, db, current_user)
    old = {"name": collection.name, "is_active": collection.is_active}

    if "name" in payload:
        name = (payload.get("name") or "").strip()
        if not name:
            raise ValidationError("A collection name is required.")
        collection.name = name[:150]
    if "description" in payload:
        collection.description = (payload.get("description") or "").strip()[:500] or None
    if "is_active" in payload:
        collection.is_active = bool(payload["is_active"])

    await _audit(
        db,
        action=AuditAction.UPDATE,
        entity_type="kb_collection",
        entity_id=str(collection.id),
        user=current_user,
        request=request,
        old_values=old,
        new_values={"name": collection.name, "is_active": collection.is_active},
    )
    await db.commit()
    await db.refresh(collection)
    return ok(_serialize_collection(collection))


@router.put("/collections/{collection_id}/grants", summary="Set which roles may read")
async def set_grants(
    collection_id: uuid.UUID,
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Replace the grant list for a collection.

    Validated against the real `roles` table rather than a hard-coded list, so
    a typo becomes a 400 instead of a grant that silently matches nobody —
    `role_name` is free text in the schema and a mismatch fails open-looking
    (the collection appears granted, and nobody can read it).
    """
    collection = await _manageable_collection(collection_id, db, current_user)

    requested = payload.get("roles")
    if not isinstance(requested, list):
        raise ValidationError("`roles` must be a list of role names.")
    requested_names = {str(r).strip() for r in requested if str(r).strip()}

    known = {
        name for (name,) in (await db.execute(select(Role.name))).all()
    }
    unknown = requested_names - known
    if unknown:
        raise ValidationError(
            f"Unknown role(s): {', '.join(sorted(unknown))}. Valid roles: "
            f"{', '.join(sorted(known))}."
        )

    # Roles that cannot query the knowledge base at all would produce a grant
    # that can never be exercised. Refusing is clearer than storing a lie.
    ungrantable = requested_names - set(authz.KB_QUERY_ROLES)
    if ungrantable:
        raise ValidationError(
            f"Role(s) {', '.join(sorted(ungrantable))} cannot query the "
            "knowledge base, so granting them access would have no effect. "
            f"Grantable roles: {', '.join(sorted(authz.KB_QUERY_ROLES))}."
        )

    existing = list(
        (
            await db.execute(
                select(KBCollectionGrant).where(
                    KBCollectionGrant.collection_id == collection.id
                )
            )
        )
        .scalars()
        .all()
    )
    old_names = sorted(g.role_name for g in existing)

    for grant in existing:
        if grant.role_name not in requested_names:
            await db.delete(grant)
    for name in requested_names - set(old_names):
        db.add(
            KBCollectionGrant(
                collection_id=collection.id,
                role_name=name,
                granted_by_id=current_user.id,
            )
        )

    await _audit(
        db,
        action=AuditAction.UPDATE,
        entity_type="kb_collection_grant",
        entity_id=str(collection.id),
        user=current_user,
        request=request,
        old_values={"roles": old_names},
        new_values={"roles": sorted(requested_names)},
    )
    await db.commit()

    refreshed = await db.get(KBCollection, collection.id)
    return ok(_serialize_collection(refreshed))  # type: ignore[arg-type]


@router.delete("/collections/{collection_id}", summary="Delete a collection")
async def delete_collection(
    collection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    collection = await _manageable_collection(collection_id, db, current_user)

    documents = list(
        (
            await db.execute(
                select(KBDocument).where(KBDocument.collection_id == collection.id)
            )
        )
        .scalars()
        .unique()
        .all()
    )
    service = KBIngestionService(db)
    keys = [v.s3_key for d in documents for v in d.versions]

    await _audit(
        db,
        action=AuditAction.DELETE,
        entity_type="kb_collection",
        entity_id=str(collection.id),
        user=current_user,
        request=request,
        old_values={"name": collection.name, "documents": len(documents)},
    )
    await db.delete(collection)
    await db.commit()

    for key in keys:
        try:
            await service.storage.delete(key)
        except Exception as exc:  # pragma: no cover - best effort
            log.warning("kb.object_delete_failed", key=key, error=str(exc))

    return ok({"deleted": True, "documents_removed": len(documents)})


# ---------------------------------------------------------------------------
# Documents
# ---------------------------------------------------------------------------

@router.get("/collections/{collection_id}/documents", summary="List documents")
async def list_documents(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    if authz.can_manage_knowledge_base(current_user):
        collection = await db.get(KBCollection, collection_id)
        if collection is None:
            raise NotFoundError("Collection not found.")
    else:
        authz.assert_can_query_knowledge_base(current_user)
        collection = await _readable_collection(collection_id, db, current_user)

    documents = list(
        (
            await db.execute(
                select(KBDocument)
                .where(KBDocument.collection_id == collection.id)
                .order_by(KBDocument.created_at.desc())
            )
        )
        .scalars()
        .unique()
        .all()
    )
    return ok([_serialize_document(d) for d in documents])


@router.post(
    "/collections/{collection_id}/documents",
    status_code=status.HTTP_201_CREATED,
    summary="Upload a document",
)
async def upload_document(
    collection_id: uuid.UUID,
    request: Request,
    file: UploadFile = File(...),
    title: str | None = Form(None),
    document_id: uuid.UUID | None = Form(None),
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Upload a new document, or a new version of an existing one.

    Ingestion is synchronous — see `kb_ingestion_service` for why. A failure
    after the bytes are stored leaves a FAILED version with the reason on it
    and the previous version still serving, so the response is a 400 describing
    what went wrong rather than a silent partial index.
    """
    collection = await _manageable_collection(collection_id, db, current_user)

    if not settings.KB_ENABLED:
        raise ValidationError("The knowledge base is disabled (KB_ENABLED=false).")

    data = await file.read()
    # Validate before storing so a rejected file never reaches object storage.
    validate_kb_upload(file.filename or "", file.content_type or "", len(data))

    existing_document = None
    if document_id is not None:
        existing_document = await db.get(KBDocument, document_id)
        if existing_document is None or existing_document.collection_id != collection.id:
            raise NotFoundError("Document not found in this collection.")

    service = KBIngestionService(db)
    try:
        document, version, duplicate = await service.ingest(
            collection=collection,
            filename=file.filename or "document",
            content_type=file.content_type or "application/octet-stream",
            data=data,
            user=current_user,
            title=title,
            document=existing_document,
        )
    except ValidationError:
        raise
    except Exception as exc:
        log.warning("kb.upload_failed", error=str(exc), collection_id=str(collection.id))
        raise ValidationError(f"The document could not be indexed: {exc}") from exc

    await _audit(
        db,
        action=AuditAction.CREATE,
        entity_type="kb_document",
        entity_id=str(document.id),
        user=current_user,
        request=request,
        new_values={
            "title": document.title,
            "collection": collection.name,
            "version_no": version.version_no,
            "chunks": version.chunk_count,
            "duplicate": duplicate,
        },
    )
    await db.commit()
    await db.refresh(document)

    return ok({**_serialize_document(document), "was_duplicate": duplicate})


@router.get(
    "/documents/{document_id}/download", summary="Download the original document"
)
async def download_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> StreamingResponse:
    """Stream the stored bytes.

    Goes through the permission check on every request rather than handing out
    a presigned URL, matching the decision already made for ticket
    attachments: a presigned URL is a bearer token that outlives the session
    and survives in browser history and proxy logs.
    """
    document = await db.get(KBDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")

    if not authz.can_manage_knowledge_base(current_user):
        authz.assert_can_query_knowledge_base(current_user)
        await _readable_collection(document.collection_id, db, current_user)

    version = next(
        (v for v in document.versions if v.id == document.active_version_id),
        None,
    ) or next(iter(sorted(document.versions, key=lambda v: v.version_no, reverse=True)), None)
    if version is None:
        raise NotFoundError("This document has no stored content.")

    try:
        data = await StorageService().download(version.s3_key)
    except Exception as exc:
        log.exception("kb.download_failed", key=version.s3_key)
        raise NotFoundError("The stored file could not be read.") from exc

    await _audit(
        db,
        action=AuditAction.VIEW,
        entity_type="kb_document",
        entity_id=str(document.id),
        user=current_user,
        request=request,
        metadata_={"version_no": version.version_no},
    )
    await db.commit()

    import io

    return StreamingResponse(
        io.BytesIO(data),
        media_type=document.content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{document.original_filename}"'
        },
    )


@router.post("/documents/{document_id}/reindex", summary="Re-index a document")
async def reindex_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Re-run parse/chunk/embed over the current version's stored bytes.

    The recovery path for a version left FAILED by a model outage, and the way
    to rebuild vectors after the embedding model changes.
    """
    authz.assert_can_manage_knowledge_base(current_user)
    document = await db.get(KBDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")

    version = next(
        iter(sorted(document.versions, key=lambda v: v.version_no, reverse=True)), None
    )
    if version is None:
        raise NotFoundError("This document has no stored content to re-index.")

    extension = version.s3_key.rsplit(".", 1)[-1].lower()

    # Drop the previous chunk rows for this version, or the (version, ordinal)
    # unique constraint rejects the rebuild on its first insert.
    await db.execute(KBChunk.__table__.delete().where(KBChunk.version_id == version.id))
    version.embedded_count = 0
    version.chunk_count = 0
    version.embedding_model = settings.KB_EMBEDDING_MODEL
    await db.commit()

    service = KBIngestionService(db)
    try:
        version = await service.process_version(document, version, extension=extension)
    except Exception as exc:
        raise ValidationError(f"Re-indexing failed: {exc}") from exc

    await _audit(
        db,
        action=AuditAction.UPDATE,
        entity_type="kb_document",
        entity_id=str(document.id),
        user=current_user,
        request=request,
        new_values={"reindexed_version": version.version_no, "chunks": version.chunk_count},
    )
    await db.commit()
    await db.refresh(document)
    return ok(_serialize_document(document))


@router.delete("/documents/{document_id}", summary="Delete a document")
async def delete_document(
    document_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    authz.assert_can_manage_knowledge_base(current_user)
    document = await db.get(KBDocument, document_id)
    if document is None:
        raise NotFoundError("Document not found.")

    await _audit(
        db,
        action=AuditAction.DELETE,
        entity_type="kb_document",
        entity_id=str(document.id),
        user=current_user,
        request=request,
        old_values={"title": document.title},
    )
    await db.commit()

    await KBIngestionService(db).delete_document(document)
    return ok({"deleted": True})


# ---------------------------------------------------------------------------
# Query
# ---------------------------------------------------------------------------

@router.post("/query", summary="Ask the knowledge base a question")
async def query_knowledge_base(
    payload: dict,
    request: Request,
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """Answer from granted collections only, with validated citations.

    Always 200, even when abstaining: "I don't have enough grounded
    information" is a successful outcome of this endpoint, not an error, and
    the UI renders it the same way it renders an answer.
    """
    authz.assert_can_query_knowledge_base(current_user)

    # One local model serves every AI path; an unthrottled KB query would
    # starve chat and email intake.
    check_rate_limit(str(current_user.id), limit=settings.AI_RATE_LIMIT_PER_MINUTE)

    question = (payload.get("question") or "").strip()
    if not question:
        raise ValidationError("A question is required.")
    if len(question) > 2000:
        raise ValidationError("Question is too long — keep it under 2000 characters.")

    result = await KBRetrievalService(db).answer(current_user, question)

    cited = set(result.cited_chunk_ids)
    sources = [
        {
            "chunk_id": str(p.chunk_id),
            "document_id": str(p.document_id),
            "document_title": p.document_title,
            "heading_path": p.heading_path,
            "page_from": p.page_from,
            "page_to": p.page_to,
            "similarity": p.similarity,
            "cited": p.chunk_id in cited,
            "marker": i,
            "excerpt": p.content[:400],
        }
        for i, p in enumerate(result.passages, start=1)
    ]

    return ok(
        {
            "question": question,
            "answer": result.answer,
            "abstained": result.abstained,
            "abstain_reason": result.abstain_reason,
            # Band is computed server-side and sent as a label so the client
            # never re-derives it from the number. The ticket AI badge drifted
            # from its backend thresholds exactly that way.
            "confidence": result.confidence,
            "confidence_band": result.confidence_band,
            "sources": sources,
            "rejected_citations": result.rejected_citations,
            "error": result.error,
            "timing": {
                "retrieval_ms": result.retrieval_ms,
                "total_ms": result.total_ms,
            },
        }
    )


@router.get("/status", summary="Knowledge-base readiness and counts")
async def kb_status(
    db: AsyncSession = Depends(get_session),
    current_user: User = Depends(get_current_user),
) -> dict:
    """What an administrator needs to see before trusting an answer."""
    authz.assert_can_query_knowledge_base(current_user)

    accessible = accessible_collections(current_user)
    collections = (
        await db.execute(select(func.count()).select_from(accessible.subquery()))
    ).scalar_one()
    chunks = (
        await db.execute(
            select(func.count(KBChunk.id)).where(
                KBChunk.collection_id.in_(accessible),
                KBChunk.embedding.isnot(None),
            )
        )
    ).scalar_one()
    pending = (
        await db.execute(
            select(func.count(KBDocumentVersion.id)).where(
                KBDocumentVersion.status.in_(
                    [KBVersionStatus.PENDING.value, KBVersionStatus.PROCESSING.value]
                )
            )
        )
    ).scalar_one()
    failed = (
        await db.execute(
            select(func.count(KBDocumentVersion.id)).where(
                KBDocumentVersion.status == KBVersionStatus.FAILED.value
            )
        )
    ).scalar_one()

    return ok(
        {
            "enabled": settings.KB_ENABLED,
            "embedding_model": settings.KB_EMBEDDING_MODEL,
            "embedding_dim": settings.KB_EMBEDDING_DIM,
            "accessible_collections": collections,
            "indexed_chunks": chunks,
            "versions_in_progress": pending,
            "versions_failed": failed,
            "can_manage": authz.can_manage_knowledge_base(current_user),
        }
    )
