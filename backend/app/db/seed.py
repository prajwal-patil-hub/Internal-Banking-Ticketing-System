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

from datetime import datetime, timedelta, timezone

from app.core.logging import configure_logging, get_logger
from app.core.rbac import ROLE_PERMISSIONS, Permission, Role
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.branch import Branch
from app.models.category import Category
from app.models.role import Permission as PermissionModel
from app.models.role import Role as RoleModel
from app.models.role import RolePermission
from app.models.sla import SLAPolicy, SLATracking
from app.models.ticket import Ticket
from app.models.user import User

log = get_logger("seed")

DEMO_USERS = [
    ("admin@successbank.local",      "Anna Admin",      Role.ADMIN),
    ("supervisor@successbank.local", "Sam Supervisor",  Role.SUPERVISOR),
    ("agent@successbank.local",      "Adam Agent",      Role.AGENT),
    ("auditor@successbank.local",    "Audrey Auditor",  Role.AUDITOR),
    ("branch@successbank.local",     "Bea Branch",      Role.BRANCH_USER),
]

DEMO_BRANCHES = [
    ("BR001", "Mumbai Fort",    "West",  "Mumbai HQ"),
    ("BR002", "Delhi CP",       "North", "Connaught Place"),
    ("BR003", "Bengaluru MG",   "South", "MG Road"),
    ("BR004", "Kolkata Park St","East",  "Park Street"),
    ("BR005", "Pune FC Road",   "West",  "FC Road"),
]

DEMO_CATEGORIES = [
    ("Core Banking",       "CBS-related issues",        "high"),
    ("ATM / Self-service", "ATM, kiosks, cash deposit", "high"),
    ("Network / Infra",    "Branch network, VPN",       "critical"),
    ("Cards & Payments",   "Card issuance, UPI, IMPS",  "high"),
    ("HR / Admin",         "Branch ops, HR support",    "low"),
]

# Banking-standard defaults (also act as fallbacks if the table is wiped).
SLA_DEFAULTS = [
    ("critical",  15,   120),
    ("high",      30,   360),
    ("medium",    60,  1440),
    ("low",      120,  4320),
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

        # 3. Grants — insert into the join table directly to avoid touching
        # the lazy-loaded `.permissions` collection from async context.
        for role_enum, perm_set in ROLE_PERMISSIONS.items():
            role = roles_by_name[role_enum.value]
            existing_perm_ids = set(
                (
                    await session.execute(
                        select(RolePermission.permission_id).where(
                            RolePermission.role_id == role.id
                        )
                    )
                ).scalars().all()
            )
            for perm_enum in perm_set:
                perm = perms_by_code[perm_enum.value]
                if perm.id not in existing_perm_ids:
                    session.add(RolePermission(role_id=role.id, permission_id=perm.id))
            await session.flush()

        # 4. Demo branches
        branches_by_code: dict[str, Branch] = {}
        for code, name, region, address in DEMO_BRANCHES:
            existing = (
                await session.execute(select(Branch).where(Branch.code == code))
            ).scalar_one_or_none()
            if existing:
                branches_by_code[code] = existing
                continue
            b = Branch(code=code, name=name, region=region, address=address)
            session.add(b)
            await session.flush()
            branches_by_code[code] = b
            log.info("seed_branch_created", code=code)

        # 5. Demo categories
        categories_by_name: dict[str, Category] = {}
        for name, desc, prio in DEMO_CATEGORIES:
            existing = (
                await session.execute(select(Category).where(Category.name == name))
            ).scalar_one_or_none()
            if existing:
                categories_by_name[name] = existing
                continue
            c = Category(name=name, description=desc, default_priority=prio)
            session.add(c)
            await session.flush()
            categories_by_name[name] = c
            log.info("seed_category_created", name=name)

        # 6. Demo users (branch_user is bound to BR001)
        users_by_email: dict[str, User] = {}
        for email, name, role_enum in DEMO_USERS:
            existing = (
                await session.execute(select(User).where(User.email == email))
            ).scalar_one_or_none()
            if existing:
                users_by_email[email] = existing
                continue
            password = secrets.token_urlsafe(12)
            user = User(
                email=email,
                full_name=name,
                password_hash=hash_password(password),
                role_id=roles_by_name[role_enum.value].id,
                branch_id=branches_by_code["BR001"].id if role_enum == Role.BRANCH_USER else None,
            )
            session.add(user)
            await session.flush()
            users_by_email[email] = user
            log.info("seed_user_created", email=email, role=role_enum.value, password=password)
            # Belt-and-braces: also print the credential cleanly to stdout so
            # `make seed > seed-output.txt` always yields a file the operator
            # can read in Notepad regardless of structlog config.
            print(f"DEMO_USER  email={email}  role={role_enum.value}  password={password}", flush=True)

        # 7. SLA policies — banking-standard defaults.
        for prio, response_min, resolution_min in SLA_DEFAULTS:
            existing = (
                await session.execute(select(SLAPolicy).where(SLAPolicy.priority == prio))
            ).scalar_one_or_none()
            if existing is None:
                session.add(SLAPolicy(
                    priority=prio,
                    response_minutes=response_min,
                    resolution_minutes=resolution_min,
                ))
                log.info("seed_sla_policy_created", priority=prio)

        # 8. A few demo tickets so the dashboard has rows on first run.
        existing_tickets = (
            await session.execute(select(Ticket))
        ).scalars().first()
        if existing_tickets is None:
            now = datetime.now(timezone.utc)
            samples = [
                ("CBS unable to post EOD", "End-of-day batch failed at 22:18.",  "critical", "Core Banking"),
                ("ATM ID 4421 cash out",    "Front-lobby ATM reporting empty.",   "high",     "ATM / Self-service"),
                ("VPN flapping at branch",  "Tunnels reset every ~6 minutes.",    "critical", "Network / Infra"),
                ("UPI mandate creation",    "Customer mandates failing.",          "high",     "Cards & Payments"),
                ("Printer ribbon order",    "Pass-book printer needs ribbon.",     "low",      "HR / Admin"),
            ]
            for i, (title, desc, prio, cat) in enumerate(samples):
                resolution = next(r for p, _, r in SLA_DEFAULTS if p == prio)
                due_at = now + timedelta(minutes=resolution)
                t = Ticket(
                    ticket_no=f"TKT-{now.year}-{i + 1:06d}",
                    branch_id=branches_by_code["BR001"].id,
                    raised_by=users_by_email["branch@successbank.local"].id,
                    category_id=categories_by_name[cat].id,
                    title=title,
                    description=desc,
                    priority=prio,
                    status="new",
                    sla_due_at=due_at,
                )
                session.add(t)
                await session.flush()
                session.add(SLATracking(
                    ticket_id=t.id,
                    policy_priority=prio,
                    due_at=due_at,
                ))

        await session.commit()
        log.info("seed_complete")


if __name__ == "__main__":
    asyncio.run(main())
