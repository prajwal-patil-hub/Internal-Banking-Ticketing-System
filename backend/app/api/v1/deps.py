"""Shared FastAPI dependencies for v1 API."""

from __future__ import annotations

from collections.abc import AsyncGenerator, Iterable

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AuthenticationError, AuthorizationError
from app.core.security import decode_token
from app.db.session import get_db
from app.models.user import User
from app.repositories.user_repo import UserRepository

_bearer = HTTPBearer(auto_error=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async for s in get_db():
        yield s


async def get_current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: AsyncSession = Depends(get_session),
) -> User:
    if creds is None:
        raise AuthenticationError("Missing bearer token.")
    try:
        payload = decode_token(creds.credentials)
    except Exception as e:  # noqa: BLE001
        raise AuthenticationError("Invalid or expired token.") from e

    if payload.get("type") != "access":
        raise AuthenticationError("Wrong token type.")

    user_id = payload.get("sub")
    if not user_id:
        raise AuthenticationError("Malformed token.")

    user = await UserRepository(db).get_by_id(user_id)  # type: ignore[arg-type]
    if user is None or not user.is_active:
        raise AuthenticationError("Account unavailable.")

    request.state.actor_id = str(user.id)
    request.state.actor_role = user.role.name
    return user


def require_roles(*roles: str):
    """Dependency factory: allow only the given role names."""
    allowed = set(roles)

    async def _dep(user: User = Depends(get_current_user)) -> User:
        if user.role.name not in allowed:
            raise AuthorizationError(
                f"Role '{user.role.name}' is not allowed for this operation."
            )
        return user

    return _dep


def require_permissions(*codes: str):
    """Dependency factory: require ALL given permission codes for the user's role."""
    needed = set(codes)

    async def _dep(
        user: User = Depends(get_current_user),
        db: AsyncSession = Depends(get_session),
    ) -> User:
        from app.repositories.user_repo import RoleRepository

        granted = await RoleRepository(db).get_permission_codes(user.role_id)
        missing: Iterable[str] = needed - granted
        if missing:
            raise AuthorizationError(
                "Missing permissions.",
                details={"missing": sorted(missing)},
            )
        return user

    return _dep
