"""User and refresh-token repositories. Pure data access — no business rules."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import LoginAttempt, RefreshToken
from app.models.role import Permission, Role
from app.models.user import User


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(User.email == email.lower())
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self.db.get(User, user_id)

    async def update(self, user: User) -> User:
        await self.db.flush()
        return user


class RoleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_name(self, name: str) -> Role | None:
        stmt = select(Role).where(Role.name == name)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def get_permission_codes(self, role_id: uuid.UUID) -> set[str]:
        stmt = (
            select(Permission.code)
            .join_from(Permission, Role.permissions)
            .where(Role.id == role_id)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        return set(rows)


class RefreshTokenRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, token: RefreshToken) -> RefreshToken:
        self.db.add(token)
        await self.db.flush()
        return token

    async def get_by_hash(self, token_hash: str) -> RefreshToken | None:
        stmt = select(RefreshToken).where(RefreshToken.token_hash == token_hash)
        return (await self.db.execute(stmt)).scalar_one_or_none()

    async def revoke(self, token: RefreshToken, *, replaced_by: uuid.UUID | None = None) -> None:
        token.revoked_at = datetime.now(UTC)
        token.replaced_by = replaced_by

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        stmt = select(RefreshToken).where(
            RefreshToken.user_id == user_id, RefreshToken.revoked_at.is_(None)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        now = datetime.now(UTC)
        for r in rows:
            r.revoked_at = now


class LoginAttemptRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def record(self, attempt: LoginAttempt) -> None:
        self.db.add(attempt)
        await self.db.flush()
