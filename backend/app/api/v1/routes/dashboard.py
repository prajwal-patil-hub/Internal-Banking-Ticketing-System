"""Dashboard endpoint — one round trip, role-aware."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session
from app.models.user import User
from app.schemas.envelope import ok
from app.services.dashboard_service import DashboardService

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview")
async def overview(
    db: AsyncSession = Depends(get_session),
    user: User = Depends(get_current_user),
) -> dict:
    svc = DashboardService(db)
    return ok(
        {
            "kpis": await svc.kpis(user),
            "recent": await svc.recent(user),
            "role_specific": await svc.role_specific(user),
        }
    )
