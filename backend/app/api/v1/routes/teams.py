from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.deps import get_current_user, get_session, require_permissions
from app.core.exceptions import ConflictError, NotFoundError
from app.models.team import Team, TeamMember
from app.models.user import User
from app.repositories.team_repo import TeamRepository
from app.repositories.user_repo import UserRepository
from app.schemas.envelope import ok, paginated
from app.schemas.team import TeamCreate, TeamMemberRef, TeamPublic, TeamUpdate
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


@router.patch("/{team_id}")
async def update_team(
    team_id: uuid.UUID,
    payload: TeamUpdate,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    t = await TeamRepository(db).get(team_id)
    if t is None:
        raise NotFoundError("Team not found.")
    fields = payload.model_dump(exclude_unset=True)
    for field, value in fields.items():
        if field == "is_active" and value is None:
            continue
        if value is None and field != "is_active":
            continue
        setattr(t, field, value)
    await db.commit()
    return ok(TeamPublic.model_validate(t).model_dump(mode="json"))


@router.delete("/{team_id}")
async def deactivate_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    t = await TeamRepository(db).get(team_id)
    if t is None:
        raise NotFoundError("Team not found.")
    t.is_active = False
    await db.commit()
    return ok(TeamPublic.model_validate(t).model_dump(mode="json"))


@router.post("/{team_id}/restore")
async def restore_team(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    t = await TeamRepository(db).get(team_id)
    if t is None:
        raise NotFoundError("Team not found.")
    t.is_active = True
    await db.commit()
    return ok(TeamPublic.model_validate(t).model_dump(mode="json"))


# ────────────────────────── members ──────────────────────────

@router.get("/{team_id}/members")
async def list_members(
    team_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(get_current_user),
) -> dict:
    if await TeamRepository(db).get(team_id) is None:
        raise NotFoundError("Team not found.")
    stmt = (
        select(User)
        .join(TeamMember, TeamMember.user_id == User.id)
        .where(TeamMember.team_id == team_id)
        .order_by(User.full_name)
    )
    users = (await db.execute(stmt)).scalars().all()
    return ok(
        [
            TeamMemberRef(
                user_id=u.id,
                full_name=u.full_name,
                email=u.email,
                role=u.role.name if u.role else "",
            ).model_dump(mode="json")
            for u in users
        ]
    )


@router.post("/{team_id}/members/{user_id}")
async def add_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    if await TeamRepository(db).get(team_id) is None:
        raise NotFoundError("Team not found.")
    if await UserRepository(db).get_by_id(user_id) is None:
        raise NotFoundError("User not found.")
    existing = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ConflictError("User is already a member of this team.")
    db.add(TeamMember(team_id=team_id, user_id=user_id))
    await db.commit()
    return ok({"added": True})


@router.delete("/{team_id}/members/{user_id}")
async def remove_member(
    team_id: uuid.UUID,
    user_id: uuid.UUID,
    db: AsyncSession = Depends(get_session),
    _user: User = Depends(require_permissions("team.manage")),
) -> dict:
    existing = (
        await db.execute(
            select(TeamMember).where(
                TeamMember.team_id == team_id, TeamMember.user_id == user_id,
            )
        )
    ).scalar_one_or_none()
    if existing is None:
        raise NotFoundError("Membership not found.")
    await db.delete(existing)
    await db.commit()
    return ok({"removed": True})
