"""SLA endpoints — policies + breached tickets."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session, require_permissions
from app.models.user import User
from app.repositories.sla_repo import SLAPolicyRepository, SLATrackingRepository
from app.schemas.envelope import ok
from app.schemas.sla import SLAPolicyPublic, SLATrackingPublic

router = APIRouter(prefix="/sla", tags=["sla"])


@router.get("/policies")
async def list_policies(
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("sla.monitor")),
) -> dict:
    rows = await SLAPolicyRepository(db).list()
    return ok([SLAPolicyPublic.model_validate(r).model_dump(mode="json") for r in rows])


@router.get("/breaches")
async def list_breaches(
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("sla.monitor")),
) -> dict:
    repo = SLATrackingRepository(db)
    rows = await repo.list_breached(limit=100)
    total = await repo.count_breached()
    return ok(
        {
            "items": [SLATrackingPublic.model_validate(r).model_dump(mode="json") for r in rows],
            "total": total,
        }
    )
