"""Idempotent database seeder.

Run via:  python -m app.db.seed

Creates:
  - role rows for every Role enum value
  - permission rows for every Permission enum value
  - role -> permission grants per ROLE_PERMISSIONS matrix
  - one demo user per role (passwords printed on first run only)
"""

from __future__ import annotations

import asyncio
import secrets

from sqlalchemy import select

from app.core.logging import configure_logging, get_logger
from app.core.rbac import ROLE_PERMISSIONS, Permission, Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Permission as PermissionModel
from app.models.role import Role as RoleModel
from app.models.user import User

log = get_logger("seed")

DEMO_USERS = [
    ("admin@successbank.local",      "Anna Admin",      Role.ADMIN),
    ("supervisor@successbank.local", "Sam Supervisor",  Role.SUPERVISOR),
    ("agent@successbank.local",      "Adam Agent",      Role.AGENT),
    ("auditor@successbank.local",    "Audrey Auditor",  Role.AUDITOR),
    ("branch@successbank.local",     "Bea Branch",      Role.BRANCH_USER),
]


async def _ensure_role(session, name: Role) -> RoleModel:
    existing = (
        await session.execute(select(RoleModel).where(RoleModel.name == name.value))
    ).scalar_one_or_none()
    if existing:
        return existing
    role = RoleModel(name=name.value, description=name.value.replace("_", " ").title())
    session.add(role)
    await session.flush()
    return role


async def _ensure_permission(session, code: Permission) -> PermissionModel:
    existing = (
        await session.execute(
            select(PermissionModel).where(PermissionModel.code == code.value)
        )
    ).scalar_one_or_none()
    if existing:
        return existing
    perm = PermissionModel(code=code.value, description=code.value)
    session.add(perm)
    await session.flush()
    return perm


async def main() -> None:
    configure_logging()
    async with SessionLocal() as session:
        # 1. Roles
        roles_by_name: dict[str, RoleModel] = {}
        for r in Role:
            roles_by_name[r.value] = await _ensure_role(session, r)

        # 2. Permissions
        perms_by_code: dict[str, PermissionModel] = {}
        for p in Permission:
            perms_by_code[p.value] = await _ensure_permission(session, p)

        # 3. Grants
        for role_enum, perm_set in ROLE_PERMISSIONS.items():
            role = roles_by_name[role_enum.value]
            current = {p.code for p in role.permissions}
            for perm_enum in perm_set:
                if perm_enum.value not in current:
                    role.permissions.append(perms_by_code[perm_enum.value])

        # 4. Demo users
        for email, name, role_enum in DEMO_USERS:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing:
                continue
            password = secrets.token_urlsafe(12)
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role_id=roles_by_name[role_enum.value].id,
            )
            session.add(user)
            log.info("seed_user_created", email=email, role=role_enum.value, password=password)

        await session.commit()
        log.info("seed_complete")


if __name__ == "__main__":
    asyncio.run(main())
