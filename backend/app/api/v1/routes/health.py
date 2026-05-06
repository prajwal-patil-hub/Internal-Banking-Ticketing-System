"""Liveness / readiness probes."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_session
from app.schemas.envelope import ok

router = APIRouter(tags=["health"])


@router.get("/healthz")
async def healthz() -> dict:
    """Liveness — process is up."""
    return ok({"status": "alive"})


@router.get("/readyz")
async def readyz(db: AsyncSession = Depends(get_session)) -> dict:
    """Readiness — DB reachable."""
    await db.execute(text("SELECT 1"))
    return ok({"status": "ready"})
