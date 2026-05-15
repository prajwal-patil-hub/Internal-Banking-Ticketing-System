"""Create a default admin user for local development.

Usage (from project root):

    docker compose -f infra/docker-compose.yml exec backend python -m scripts.seed_admin

Credentials:
    email:    admin@example.com
    password: Admin@1234
"""

from __future__ import annotations

import asyncio
import uuid

from sqlalchemy import select

from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.role import Role
from app.models.user import User

EMAIL = "admin@example.com"
PASSWORD = "Admin@1234"
ROLE_NAME = "admin"


async def main() -> None:
    async with SessionLocal() as db:
        role = (
            await db.execute(select(Role).where(Role.name == ROLE_NAME))
        ).scalar_one_or_none()
        if role is None:
            role = Role(id=uuid.uuid4(), name=ROLE_NAME, description="Administrator")
            db.add(role)
            await db.flush()

        user = (
            await db.execute(select(User).where(User.email == EMAIL))
        ).scalar_one_or_none()
        if user is None:
            db.add(
                User(
                    id=uuid.uuid4(),
                    email=EMAIL,
                    full_name="Admin",
                    password_hash=hash_password(PASSWORD),
                    role_id=role.id,
                    is_active=True,
                )
            )
            print(f"Created {EMAIL} / {PASSWORD}")
        else:
            print(f"{EMAIL} already exists; leaving it alone.")

        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
