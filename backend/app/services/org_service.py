"""Org hierarchy service: subtree queries and hierarchy operations."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.org import OrgUnit
from app.models.user import User


async def get_subtree_ids(db: AsyncSession, root_id: uuid.UUID) -> list[uuid.UUID]:
    """Return all org unit IDs in the subtree rooted at root_id (inclusive)."""
    ids: list[uuid.UUID] = []
    queue: list[uuid.UUID] = [root_id]
    while queue:
        current = queue.pop()
        ids.append(current)
        result = await db.execute(
            select(OrgUnit.id).where(OrgUnit.parent_id == current)
        )
        children = result.scalars().all()
        queue.extend(children)
    return ids


async def can_user_manage_unit(user: User, target_org_unit_id: uuid.UUID, db: AsyncSession) -> bool:
    """Check if the user has management rights over the given org unit."""
    if user.is_super_admin:
        return True
    if not user.org_unit_id or not user.org_role:
        return False
    if not (user.org_role.can_manage_unit or user.org_role.can_manage_subtree):
        return False
    # can_manage_unit: manage only their own org unit
    if user.org_role.can_manage_unit and not user.org_role.can_manage_subtree:
        return str(user.org_unit_id) == str(target_org_unit_id)
    # can_manage_subtree: manage their org unit and all descendants
    subtree = await get_subtree_ids(db, user.org_unit_id)
    return target_org_unit_id in subtree


async def get_accessible_org_unit_ids(user: User, db: AsyncSession) -> list[uuid.UUID] | None:
    """Return which org unit IDs this user can see tickets for, or None for unrestricted."""
    if user.is_super_admin:
        return None
    if not user.org_unit_id:
        return None
    if user.org_role and user.org_role.can_manage_subtree:
        return await get_subtree_ids(db, user.org_unit_id)
    # Regular users: only their own org unit
    return [user.org_unit_id]


async def get_hierarchy_chain(db: AsyncSession, org_unit_id: uuid.UUID) -> list[dict]:
    """Walk up the parent chain and return [{name, code, level}] from root to leaf."""
    chain: list[dict] = []
    current_id: uuid.UUID | None = org_unit_id
    visited: set[str] = set()
    while current_id and str(current_id) not in visited:
        visited.add(str(current_id))
        result = await db.execute(select(OrgUnit).where(OrgUnit.id == current_id))
        unit = result.scalar_one_or_none()
        if not unit:
            break
        chain.append({
            "id": str(unit.id),
            "name": unit.name,
            "code": unit.code,
            "level": unit.hierarchy_level.name if unit.hierarchy_level else None,
        })
        current_id = unit.parent_id
    chain.reverse()
    return chain
