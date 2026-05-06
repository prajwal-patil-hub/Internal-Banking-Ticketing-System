"""User-self endpoints. Admin user management lands later (P2)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.api.v1.deps import get_current_user
from app.models.user import User
from app.schemas.auth import UserPublic
from app.schemas.envelope import ok

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me")
async def me(user: User = Depends(get_current_user)) -> dict:
    return ok(
        UserPublic.model_validate(
            {
                "id": user.id,
                "email": user.email,
                "full_name": user.full_name,
                "role": user.role.name,
                "branch_id": user.branch_id,
                "mfa_enabled": user.mfa_enabled,
            }
        ).model_dump(mode="json")
    )
