"""Idempotent dev seed — creates default roles and an admin user.

Run automatically on container startup via docker-compose. Safe to re-run:
skips any entity that already exists.

Default admin credentials:
  Email:    admin@successbank.local
  Password: Admin@123456
"""

from __future__ import annotations

import asyncio
import sys
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.role import Role
from app.models.user import User

ROLES = [
    ("admin",       "Full access — manage users, config, and all tickets"),
    ("supervisor",  "Oversee agents, view SLA reports, escalate tickets"),
    ("agent",       "Handle and resolve tickets"),
    ("auditor",     "Read-only access to tickets and audit logs"),
    ("branch_user", "Raise tickets on behalf of a branch"),
]

ADMIN_EMAIL    = "admin@successbank.local"
ADMIN_PASSWORD = "Admin@123456"
ADMIN_NAME     = "System Admin"


async def seed(db: AsyncSession) -> None:
    # --- Roles ---------------------------------------------------------------
    existing = {r.name for r in (await db.execute(select(Role))).scalars().all()}
    created_roles: list[str] = []
    for name, description in ROLES:
        if name not in existing:
            db.add(Role(id=uuid.uuid4(), name=name, description=description))
            created_roles.append(name)
    if created_roles:
        await db.flush()
        print(f"  [seed] Created roles: {', '.join(created_roles)}")
    else:
        print("  [seed] Roles already exist — skipped")

    # --- Admin user ----------------------------------------------------------
    admin_role = (await db.execute(select(Role).where(Role.name == "admin"))).scalar_one()
    existing_admin = (
        await db.execute(select(User).where(User.email == ADMIN_EMAIL))
    ).scalar_one_or_none()

    if existing_admin is None:
        db.add(
            User(
                id=uuid.uuid4(),
                email=ADMIN_EMAIL,
                full_name=ADMIN_NAME,
                password_hash=hash_password(ADMIN_PASSWORD),
                role_id=admin_role.id,
                is_active=True,
            )
        )
        await db.flush()
        print(f"  [seed] Admin user created: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    else:
        print(f"  [seed] Admin user already exists ({ADMIN_EMAIL}) — skipped")

    await db.commit()


async def main() -> None:
    print("[seed] Starting dev seed…")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as db:
        await seed(db)
    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
