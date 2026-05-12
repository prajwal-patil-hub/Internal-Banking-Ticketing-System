"""End-to-end check of `RoleRepository.get_permission_codes`.

This is the query every `require_permissions(...)` dependency runs. A
malformed join here brings down every privileged write with 500 ->
"Network error" in the frontend (because the response stream is torn
before CORS headers are flushed). Keep this test green.
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.rbac import ROLE_PERMISSIONS
from app.core.rbac import Permission as PermissionEnum
from app.core.rbac import Role as RoleEnum
from app.db.base import Base
from app.models import (  # noqa: F401  ensures every mapper is registered
    audit,
    auth,
    branch,
    category,
    escalation,
    notification,
    sla,
    team,
    ticket,
    ticket_history,
    user,
)
from app.models.role import Permission, Role, RolePermission
from app.repositories.user_repo import RoleRepository


@pytest.fixture
async def session() -> AsyncSession:
    """In-memory async SQLite for isolated per-test schema."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        # JSONB columns don't compile on SQLite; this test only needs
        # roles + permissions + role_permissions, so create just those.
        await conn.run_sync(
            lambda c: Base.metadata.create_all(
                c,
                tables=[
                    Role.__table__,
                    Permission.__table__,
                    RolePermission.__table__,
                ],
            )
        )
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as s:
        yield s
    await engine.dispose()


async def test_get_permission_codes_returns_admin_grants(session: AsyncSession) -> None:
    # Seed an admin role with three known permissions.
    admin_role = Role(name=RoleEnum.ADMIN.value, description="Admin")
    perms = [
        Permission(code=PermissionEnum.BRANCH_MANAGE.value, description=""),
        Permission(code=PermissionEnum.USER_MANAGE.value, description=""),
        Permission(code=PermissionEnum.TICKET_ASSIGN.value, description=""),
    ]
    session.add(admin_role)
    for p in perms:
        session.add(p)
    await session.flush()
    for p in perms:
        session.add(RolePermission(role_id=admin_role.id, permission_id=p.id))
    await session.commit()

    codes = await RoleRepository(session).get_permission_codes(admin_role.id)

    assert codes == {
        PermissionEnum.BRANCH_MANAGE.value,
        PermissionEnum.USER_MANAGE.value,
        PermissionEnum.TICKET_ASSIGN.value,
    }


async def test_get_permission_codes_empty_for_unknown_role(session: AsyncSession) -> None:
    import uuid
    codes = await RoleRepository(session).get_permission_codes(uuid.uuid4())
    assert codes == set()


def test_rbac_matrix_covers_every_role() -> None:
    # Sanity: every role enum value has at least one permission. Catches
    # a regressed seed matrix.
    for r in RoleEnum:
        assert r in ROLE_PERMISSIONS, f"missing role in matrix: {r}"
        assert len(ROLE_PERMISSIONS[r]) > 0, f"role {r} has zero permissions"
    _ = asyncio  # keep import for ruff
