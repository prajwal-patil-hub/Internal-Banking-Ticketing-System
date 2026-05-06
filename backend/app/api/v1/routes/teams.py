from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.models.team import Team
from app.models.user import User
from app.repositories.team_repo import TeamRepository
from app.schemas.envelope import ok, paginated
from app.schemas.team import TeamCreate, TeamPublic
from app.utils.pagination import PageParams, page_params

router = APIRouter(prefix="/teams", tags=["teams"])


@router.get("")
async def list_teams(
    p: PageParams = Depends(page_params),
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    items, total = await TeamRepository(db).list(offset=p.offset, limit=p.limit)
    return paginated(
        [TeamPublic.model_validate(t).model_dump(mode="json") for t in items],
        page=p.page, size=p.size, total=total,
    )


@router.post("")
async def create_team(
    payload: TeamCreate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    t = Team(
        name=payload.name.strip(),
        description=payload.description,
        supervisor_id=payload.supervisor_id,
    )
    await TeamRepository(db).create(t)
    await db.commit()
    return ok(TeamPublic.model_validate(t).model_dump(mode="json"))
