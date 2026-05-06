"""Auth service.

Encapsulates: login, refresh-token rotation, logout. Designed so the
controller stays a thin shell.

Security policies enforced here:
  - Account lockout after 5 consecutive failures (15-minute window).
  - Refresh-token rotation: presenting a refresh token revokes it and issues
    a new one. Reusing a revoked refresh token revokes the entire chain
    for that user (theft signal).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.core.exceptions import AuthenticationError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    needs_rehash,
    verify_password,
)
from app.models.auth import LoginAttempt, RefreshToken
from app.models.user import User
from app.repositories.user_repo import (
    LoginAttemptRepository,
    RefreshTokenRepository,
    UserRepository,
)

LOCK_THRESHOLD = 5
LOCK_DURATION = timedelta(minutes=15)


class AuthService:
    def __init__(
        self,
        users: UserRepository,
        tokens: RefreshTokenRepository,
        attempts: LoginAttemptRepository,
    ) -> None:
        self.users = users
        self.tokens = tokens
        self.attempts = attempts

    # ---- Login -----------------------------------------------------------

    async def login(
        self, *, email: str, password: str, ip: str, user_agent: str
    ) -> tuple[User, str, datetime, str, datetime]:
        email = email.lower().strip()
        user = await self.users.get_by_email(email)

        if user is None:
            await self._record_attempt(email, ip, user_agent, success=False, reason="no_user")
            raise AuthenticationError("Invalid credentials.")

        if not user.is_active:
            await self._record_attempt(email, ip, user_agent, success=False, reason="inactive")
            raise AuthenticationError("Account inactive.")

        if user.locked_until and user.locked_until > datetime.now(timezone.utc):
            await self._record_attempt(email, ip, user_agent, success=False, reason="locked")
            raise AuthenticationError("Account temporarily locked.")

        if not verify_password(password, user.password_hash):
            user.failed_login_count += 1
            if user.failed_login_count >= LOCK_THRESHOLD:
                user.locked_until = datetime.now(timezone.utc) + LOCK_DURATION
                user.failed_login_count = 0
            await self.users.update(user)
            await self._record_attempt(email, ip, user_agent, success=False, reason="bad_password")
            raise AuthenticationError("Invalid credentials.")

        # Success — reset counters, optionally rehash.
        user.failed_login_count = 0
        user.locked_until = None
        user.last_login_at = datetime.now(timezone.utc)
        if needs_rehash(user.password_hash):
            user.password_hash = hash_password(password)
        await self.users.update(user)

        await self._record_attempt(email, ip, user_agent, success=True, reason="ok")

        # Audit: successful authentication is a compliance event.
        from app.services.audit_service import AuditService  # local import avoids cycle
        await AuditService(self.users.db).log(
            actor=user,
            entity_type="user",
            entity_id=user.id,
            action="auth.login",
            new_value={"email": user.email, "role": user.role.name},
        )

        access, access_exp = create_access_token(subject=str(user.id), role=user.role.name)
        refresh_raw, refresh_exp = await self._issue_refresh(user.id, ip, user_agent)
        return user, access, access_exp, refresh_raw, refresh_exp

    # ---- Refresh ---------------------------------------------------------

    async def refresh(
        self, *, raw_token: str, ip: str, user_agent: str
    ) -> tuple[User, str, datetime, str, datetime]:
        token_hash = hash_refresh_token(raw_token)
        record = await self.tokens.get_by_hash(token_hash)

        if record is None:
            raise AuthenticationError("Invalid refresh token.")

        # Theft signal: token was already revoked but is being reused.
        if record.revoked_at is not None:
            await self.tokens.revoke_all_for_user(record.user_id)
            raise AuthenticationError("Refresh token reuse detected. Re-authenticate.")

        if record.expires_at <= datetime.now(timezone.utc):
            raise AuthenticationError("Refresh token expired.")

        user = await self.users.get_by_id(record.user_id)
        if user is None or not user.is_active:
            raise AuthenticationError("Account unavailable.")

        access, access_exp = create_access_token(subject=str(user.id), role=user.role.name)
        new_raw, new_exp = await self._issue_refresh(user.id, ip, user_agent, replaces=record)
        return user, access, access_exp, new_raw, new_exp

    # ---- Logout ----------------------------------------------------------

    async def logout(self, *, raw_token: str | None) -> None:
        if not raw_token:
            return
        record = await self.tokens.get_by_hash(hash_refresh_token(raw_token))
        if record and record.revoked_at is None:
            await self.tokens.revoke(record)

    # ---- Helpers ---------------------------------------------------------

    async def _issue_refresh(
        self,
        user_id,
        ip: str,
        user_agent: str,
        *,
        replaces: RefreshToken | None = None,
    ) -> tuple[str, datetime]:
        raw, digest, expiry = generate_refresh_token()
        new = RefreshToken(
            user_id=user_id,
            token_hash=digest,
            expires_at=expiry,
            ip_address=ip,
            user_agent=user_agent[:255],
        )
        await self.tokens.create(new)
        if replaces is not None:
            await self.tokens.revoke(replaces, replaced_by=new.id)
        return raw, expiry

    async def _record_attempt(
        self, email: str, ip: str, user_agent: str, *, success: bool, reason: str
    ) -> None:
        await self.attempts.record(
            LoginAttempt(
                email=email,
                ip_address=ip,
                user_agent=user_agent[:255],
                success=success,
                reason=reason,
            )
        )
