"""Idempotent dev seed — creates default roles, admin user, categories, and SLA policies.

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
from app.models.sla import SLAPolicy
from app.models.ticket import TicketCategory, TicketSubCategory
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

# (code, name, department, banking_domain, subcategories)
CATEGORIES = [
    ("payments", "Payments & Transfers", "Payments Operations", "payments", [
        ("payments.failed",    "Failed Transaction"),
        ("payments.delayed",   "Delayed Payment"),
        ("payments.duplicate", "Duplicate Payment"),
        ("payments.reversal",  "Payment Reversal"),
    ]),
    ("fraud", "Fraud & Security", "Risk & Compliance", "fraud", [
        ("fraud.card",         "Card Fraud"),
        ("fraud.account",      "Account Takeover"),
        ("fraud.phishing",     "Phishing Attack"),
        ("fraud.identity",     "Identity Theft"),
    ]),
    ("kyc", "KYC & Onboarding", "Compliance", "kyc", [
        ("kyc.doc_missing",    "Missing Documents"),
        ("kyc.verification",   "Identity Verification"),
        ("kyc.update",         "KYC Data Update"),
    ]),
    ("loans", "Loans & Credit", "Retail Banking", "loans", [
        ("loans.application",  "New Loan Application"),
        ("loans.repayment",    "Repayment Issue"),
        ("loans.closure",      "Loan Closure"),
        ("loans.restructure",  "Loan Restructuring"),
    ]),
    ("compliance", "Regulatory & Compliance", "Compliance", "compliance", [
        ("compliance.aml",     "AML Alert"),
        ("compliance.report",  "Regulatory Reporting"),
        ("compliance.audit",   "Internal Audit Query"),
    ]),
    ("it", "IT & Systems", "Information Technology", "it", [
        ("it.access",          "Access Request"),
        ("it.outage",          "System Outage"),
        ("it.bug",             "Software Bug"),
        ("it.security",        "Security Incident"),
    ]),
    ("operations", "Operations", "Operations", "operations", [
        ("ops.reconciliation", "Reconciliation Issue"),
        ("ops.eod",            "End-of-Day Processing"),
        ("ops.nostro",         "Nostro Account"),
    ]),
    ("treasury", "Treasury", "Treasury", "treasury", [
        ("tsy.fx",             "FX Rate Issue"),
        ("tsy.liquidity",      "Liquidity Management"),
        ("tsy.investment",     "Investment Query"),
    ]),
    ("dispute", "Disputes & Chargebacks", "Customer Service", "dispute", [
        ("dispute.chargeback", "Chargeback Request"),
        ("dispute.merchant",   "Merchant Dispute"),
        ("dispute.atm",        "ATM Dispute"),
    ]),
    ("access", "Account Access", "Customer Service", "access", [
        ("access.locked",      "Account Locked"),
        ("access.reset",       "Password / PIN Reset"),
        ("access.update",      "Contact Details Update"),
    ]),
]

# Default SLA policies (priority, response_min, resolution_min)
SLA_DEFAULTS = [
    ("critical", 30,    120),
    ("high",     90,    360),
    ("medium",   240,  1440),
    ("low",      480,  4320),
]


async def seed(db: AsyncSession) -> None:
    # --- Roles ---------------------------------------------------------------
    existing_roles = {r.name for r in (await db.execute(select(Role))).scalars().all()}
    created_roles: list[str] = []
    for name, description in ROLES:
        if name not in existing_roles:
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

    # --- Ticket categories ---------------------------------------------------
    existing_cats = {
        c.code
        for c in (await db.execute(select(TicketCategory))).scalars().all()
    }
    created_cats: list[str] = []
    for code, name, department, banking_domain, subcats in CATEGORIES:
        if code in existing_cats:
            continue
        cat = TicketCategory(
            id=uuid.uuid4(),
            code=code,
            name=name,
            department=department,
            banking_domain=banking_domain,
            description=f"{name} tickets",
            is_active=True,
        )
        db.add(cat)
        await db.flush()
        for sub_code, sub_name in subcats:
            db.add(TicketSubCategory(
                id=uuid.uuid4(),
                category_id=cat.id,
                code=sub_code,
                name=sub_name,
                description=sub_name,
                is_active=True,
            ))
        created_cats.append(code)
    if created_cats:
        await db.flush()
        print(f"  [seed] Created {len(created_cats)} categories: {', '.join(created_cats)}")
    else:
        print("  [seed] Categories already exist — skipped")

    # --- Default SLA policies ------------------------------------------------
    existing_policies = (await db.execute(
        select(SLAPolicy).where(SLAPolicy.is_default.is_(True))
    )).scalars().all()
    existing_prio = {p.priority for p in existing_policies}

    created_sla: list[str] = []
    for priority, resp_min, res_min in SLA_DEFAULTS:
        if priority not in existing_prio:
            db.add(SLAPolicy(
                id=uuid.uuid4(),
                name=f"Default {priority.capitalize()} SLA",
                priority=priority,
                response_minutes=resp_min,
                resolution_minutes=res_min,
                business_hours_only=False,
                is_default=True,
            ))
            created_sla.append(priority)
    if created_sla:
        await db.flush()
        print(f"  [seed] Created default SLA policies: {', '.join(created_sla)}")
    else:
        print("  [seed] SLA policies already exist — skipped")

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
