"""Comprehensive demo-data seeder.

Run via:  docker compose -f infra/docker-compose.yml exec backend python -m app.db.demo_seed

Idempotent: re-running skips anything that already exists (keyed by a stable
natural key per entity), so it's safe to run repeatedly.

Creates a rich, realistic dataset so every screen has something to show
without hand-creating records:

  * 5 roles + full permission matrix (delegates to app.db.seed)
  * 10 branches across regions
  * 12 users — admin/supervisor/auditor + 5 agents + 4 branch users
    ALL with the same known password:  Password@123
  * ~24 tickets spanning every status, priority, category and source,
    some assigned, some breached, some with AI fields populated
  * public + internal comments on several tickets
  * SLA tracking rows (on-time, at-risk, breached)
  * 5 escalation rules + a handful of escalation events

Login after seeding with any of:
  admin@successbank.com      / Password@123   (admin)
  supervisor@successbank.com / Password@123   (supervisor)
  auditor@successbank.com    / Password@123   (auditor)
  agent1@successbank.com     / Password@123   (agent)   ... agent1..agent5
  branch1@successbank.com    / Password@123   (branch_user) ... branch1..branch4
"""

from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select

from app.core.logging import configure_logging, get_logger
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.branch import Branch
from app.models.comment import CommentSource, TicketComment
from app.models.escalation import EscalationEvent, EscalationRule, EscalationTrigger
from app.models.role import Role as RoleModel
from app.models.sla import SLAPolicy, SLATracking
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketSource,
    TicketStatus,
)
from app.models.user import User
from app.db import seed as base_seed

log = get_logger("demo_seed")

DEMO_PASSWORD = "Password@123"
NOW = datetime.now(timezone.utc)

BRANCHES = [
    ("MUM01", "Mumbai Fort",        "West",  "Mumbai, MH",      "SUCC0000001"),
    ("DEL01", "Delhi Connaught",    "North", "New Delhi, DL",   "SUCC0000002"),
    ("BLR01", "Bangalore MG Road",  "South", "Bengaluru, KA",   "SUCC0000003"),
    ("CHN01", "Chennai T Nagar",    "South", "Chennai, TN",     "SUCC0000004"),
    ("KOL01", "Kolkata Park St",    "East",  "Kolkata, WB",     "SUCC0000005"),
    ("HYD01", "Hyderabad Banjara",  "South", "Hyderabad, TG",   "SUCC0000006"),
    ("PUN01", "Pune FC Road",       "West",  "Pune, MH",        "SUCC0000007"),
    ("AHM01", "Ahmedabad CG Road",  "West",  "Ahmedabad, GJ",   "SUCC0000008"),
    ("JAI01", "Jaipur MI Road",     "North", "Jaipur, RJ",      "SUCC0000009"),
    ("LKO01", "Lucknow Hazratganj", "North", "Lucknow, UP",     "SUCC0000010"),
]

# (email, full_name, role_name)
USERS = [
    ("admin@successbank.com",      "Anna Admin",       "admin"),
    ("supervisor@successbank.com", "Sam Supervisor",   "supervisor"),
    ("auditor@successbank.com",    "Audrey Auditor",   "auditor"),
    ("agent1@successbank.com",     "Aarav Agent",      "agent"),
    ("agent2@successbank.com",     "Bhavna Agent",     "agent"),
    ("agent3@successbank.com",     "Chetan Agent",     "agent"),
    ("agent4@successbank.com",     "Divya Agent",      "agent"),
    ("agent5@successbank.com",     "Esha Agent",       "agent"),
    ("branch1@successbank.com",    "Farhan Branch",    "branch_user"),
    ("branch2@successbank.com",    "Gita Branch",      "branch_user"),
    ("branch3@successbank.com",    "Harish Branch",    "branch_user"),
    ("branch4@successbank.com",    "Isha Branch",      "branch_user"),
]

# Ticket templates: (title, description, category_code, priority, source)
TICKET_TEMPLATES = [
    ("Unable to add security details in retail loan",
     "While adding the security details I'm getting: 'security amount should be more than the loan amount'.",
     "loans", "medium", "portal"),
    ("UPI payment failed but amount debited",
     "Customer's UPI txn of ₹4,500 failed, money debited, beneficiary not credited. Ref UPI2026XYZ.",
     "payments", "high", "email"),
    ("Suspected card-not-present fraud",
     "Three international card transactions flagged in 5 minutes on a domestic-only card.",
     "fraud", "critical", "phone"),
    ("KYC re-verification stuck at step 3",
     "Aadhaar OTP verified but PAN step keeps erroring with 'service unavailable'.",
     "kyc", "medium", "portal"),
    ("NEFT to vendor pending for 6 hours",
     "RTGS/NEFT batch shows pending, vendor escalating. Amount ₹2.3L.",
     "payments", "high", "email"),
    ("Branch teller cash drawer mismatch",
     "End-of-day cash short by ₹1,200 at counter 4, needs reconciliation.",
     "operations", "medium", "portal"),
    ("Loan EMI debited twice this month",
     "EMI of ₹18,900 debited on the 5th and again on the 7th.",
     "loans", "high", "chat"),
    ("Account statement download throws 500",
     "Net-banking statement PDF export fails for date ranges over 90 days.",
     "it", "low", "portal"),
    ("Regulatory report submission deadline reminder",
     "RBI return XBRL upload portal rejecting our filing with schema error.",
     "compliance", "critical", "email"),
    ("New employee cannot access core banking",
     "Joiner from Monday still has no CBS login; AD account active.",
     "it", "medium", "portal"),
    ("Chargeback dispute for failed ATM withdrawal",
     "ATM dispensed no cash, account debited ₹10,000. Customer wants chargeback.",
     "fraud", "high", "phone"),
    ("Customer onboarding video-KYC link expired",
     "VKYC link expires before customer joins; needs longer TTL.",
     "kyc", "low", "chat"),
]

STATUSES_CYCLE = [
    TicketStatus.NEW,
    TicketStatus.ACKNOWLEDGED,
    TicketStatus.ASSIGNED,
    TicketStatus.IN_PROGRESS,
    TicketStatus.ON_HOLD,
    TicketStatus.ESCALATED,
    TicketStatus.RESOLVED,
    TicketStatus.CLOSED,
    TicketStatus.REOPENED,
]


async def _get_or_create_branches(session) -> list[Branch]:
    out = []
    for code, name, region, address, ifsc in BRANCHES:
        existing = (
            await session.execute(select(Branch).where(Branch.code == code))
        ).scalar_one_or_none()
        if existing:
            out.append(existing)
            continue
        b = Branch(
            code=code, name=name, region=region, address=address, ifsc=ifsc,
            contact_email=f"{code.lower()}@successbank.com",
            contact_phone="+91-22-5550-" + code[-4:].rjust(4, "0"),
            is_active=True,
        )
        session.add(b)
        out.append(b)
    await session.flush()
    return out


async def _get_or_create_users(session, branches: list[Branch]) -> list[User]:
    roles = {
        r.name: r
        for r in (await session.execute(select(RoleModel))).scalars().all()
    }
    out = []
    for i, (email, name, role_name) in enumerate(USERS):
        # branch users get tied to a branch; others are cross-branch (None)
        branch_id = branches[i % len(branches)].id if role_name == "branch_user" else None
        existing = (
            await session.execute(select(User).where(User.email == email))
        ).scalar_one_or_none()
        if existing:
            # Force the known demo password so login is deterministic even if
            # the base seeder already created this email with a random one.
            existing.password_hash = hash_password(DEMO_PASSWORD)
            existing.is_active = True
            out.append(existing)
            continue
        u = User(
            email=email,
            full_name=name,
            password_hash=hash_password(DEMO_PASSWORD),
            role_id=roles[role_name].id,
            branch_id=branch_id,
            is_active=True,
        )
        session.add(u)
        out.append(u)
        log.info("demo_user", email=email, role=role_name, password=DEMO_PASSWORD)
    await session.flush()
    return out


async def _seed_tickets(session, users: list[User], branches: list[Branch]) -> list[Ticket]:
    cats = {
        c.code: c
        for c in (await session.execute(select(TicketCategory))).scalars().all()
    }
    agents = [u for u in users if u.email.startswith("agent")]
    branch_users = [u for u in users if u.email.startswith("branch")]

    tickets: list[Ticket] = []

    # Build 2 passes over templates -> ~24 tickets covering all statuses.
    # Demo tickets use a deterministic TKT-DEMO-NNN number so re-running the
    # seeder detects and skips them (idempotent).
    rng = random.Random(42)
    demo_seq = 0
    for pass_idx in range(2):
        for t_idx, (title, desc, cat_code, prio, source) in enumerate(TICKET_TEMPLATES):
            demo_seq += 1
            ticket_number = f"TKT-DEMO-{demo_seq:03d}"

            # Skip if this demo ticket already exists.
            existing = (
                await session.execute(
                    select(Ticket).where(Ticket.ticket_number == ticket_number)
                )
            ).scalar_one_or_none()
            if existing:
                tickets.append(existing)
                continue

            status = STATUSES_CYCLE[(pass_idx * len(TICKET_TEMPLATES) + t_idx) % len(STATUSES_CYCLE)]
            reporter = rng.choice(branch_users)
            assignee = None
            if status not in {TicketStatus.NEW}:
                assignee = rng.choice(agents)

            category = cats.get(cat_code)
            created = NOW - timedelta(days=rng.randint(0, 25), hours=rng.randint(0, 23))

            ticket = Ticket(
                ticket_number=ticket_number,
                title=title,
                description=desc,
                status=status,
                priority=TicketPriority(prio),
                source=TicketSource(source),
                category_id=category.id if category else None,
                reporter_id=reporter.id,
                assignee_id=assignee.id if assignee else None,
                branch_id=reporter.branch_id or branches[t_idx % len(branches)].id,
                department=category.department if category else None,
                tags=[cat_code, prio],
                sla_breached=(status in {TicketStatus.ESCALATED} or (prio == "critical" and pass_idx == 1)),
                created_at=created,
            )
            # Populate AI fields on a subset so the AI badge has data.
            if t_idx % 3 == 0:
                ticket.ai_category = cat_code
                ticket.ai_confidence = round(rng.uniform(0.7, 0.98), 2)
                ticket.ai_risk_score = round(rng.uniform(0.1, 0.95), 2)
                ticket.ai_sentiment = rng.choice(["positive", "neutral", "negative"])
                ticket.ai_summary = f"Auto-summary: {title.lower()}."
            if status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}:
                ticket.resolved_at = created + timedelta(hours=rng.randint(2, 48))
                ticket.first_response_at = created + timedelta(minutes=rng.randint(10, 120))
            if status == TicketStatus.CLOSED:
                ticket.closed_at = ticket.resolved_at + timedelta(hours=rng.randint(1, 12))

            session.add(ticket)
            tickets.append(ticket)
    await session.flush()
    return tickets


async def _seed_comments(session, tickets: list[Ticket], users: list[User]) -> None:
    agents = [u for u in users if u.email.startswith("agent")]
    branch_users = [u for u in users if u.email.startswith("branch")]
    rng = random.Random(7)

    for ticket in tickets:
        # Only add comments if none exist for this ticket yet.
        existing = (
            await session.execute(
                select(func.count(TicketComment.id)).where(
                    TicketComment.ticket_id == ticket.id
                )
            )
        ).scalar_one()
        if existing:
            continue
        if rng.random() < 0.4:
            continue  # leave some tickets comment-free

        # one public reply from an agent
        session.add(
            TicketComment(
                ticket_id=ticket.id,
                author_id=rng.choice(agents).id,
                body="Thanks for raising this — we're looking into it and will update shortly.",
                is_internal=False,
                source=CommentSource.AGENT,
                ai_generated=False,
            )
        )
        # one internal triage note
        session.add(
            TicketComment(
                ticket_id=ticket.id,
                author_id=rng.choice(agents).id,
                body="Internal: checked core-banking logs, replicated the issue, escalating to L2 if not fixed by EOD.",
                is_internal=True,
                source=CommentSource.AGENT,
                ai_generated=False,
            )
        )
    await session.flush()


async def _seed_sla_tracking(session, tickets: list[Ticket]) -> None:
    default_policy = (
        await session.execute(
            select(SLAPolicy).where(SLAPolicy.is_default == True).limit(1)  # noqa: E712
        )
    ).scalars().first()

    for ticket in tickets:
        existing = (
            await session.execute(
                select(func.count(SLATracking.id)).where(
                    SLATracking.ticket_id == ticket.id
                )
            )
        ).scalar_one()
        if existing:
            continue
        resp_due = ticket.created_at + timedelta(minutes=60)
        res_due = ticket.created_at + timedelta(minutes=480)
        session.add(
            SLATracking(
                ticket_id=ticket.id,
                policy_id=default_policy.id if default_policy else None,
                response_due_at=resp_due,
                resolution_due_at=res_due,
                first_response_at=ticket.first_response_at,
                resolved_at=ticket.resolved_at,
                is_response_breached=ticket.first_response_at is not None
                and ticket.first_response_at > resp_due,
                is_resolution_breached=ticket.sla_breached,
            )
        )
    await session.flush()


async def _seed_escalations(session, tickets: list[Ticket], users: list[User]) -> None:
    cats = {
        c.code: c
        for c in (await session.execute(select(TicketCategory))).scalars().all()
    }
    supervisor = next((u for u in users if u.email.startswith("supervisor")), None)

    rule_specs = [
        ("Critical SLA breach", EscalationTrigger.SLA_BREACH, 60, "supervisor", "critical"),
        ("Fraud auto-escalation", EscalationTrigger.HIGH_RISK, None, "supervisor", "high"),
        ("VIP customer priority", EscalationTrigger.VIP_CUSTOMER, None, "admin", None),
        ("Regulatory impact", EscalationTrigger.REGULATORY, None, "admin", None),
        ("Manual supervisor review", EscalationTrigger.MANUAL, None, "supervisor", None),
    ]
    rules: list[EscalationRule] = []
    for name, trigger, mins, role, threshold in rule_specs:
        existing = (
            await session.execute(select(EscalationRule).where(EscalationRule.name == name))
        ).scalar_one_or_none()
        if existing:
            rules.append(existing)
            continue
        r = EscalationRule(
            name=name,
            trigger=trigger,
            trigger_after_minutes=mins,
            escalate_to_role=role,
            escalate_to_user_id=supervisor.id if (supervisor and role == "supervisor") else None,
            notify_email="ops-escalations@successbank.com",
            priority_threshold=threshold,
            is_active=True,
            category_id=cats["fraud"].id if trigger == EscalationTrigger.HIGH_RISK else None,
        )
        session.add(r)
        rules.append(r)
    await session.flush()

    # Fire events on the breached/escalated tickets.
    breached = [t for t in tickets if t.sla_breached or t.status == TicketStatus.ESCALATED]
    have_events = (await session.execute(select(func.count(EscalationEvent.id)))).scalar_one()
    if have_events == 0:
        rng = random.Random(99)
        for t in breached[:8]:
            session.add(
                EscalationEvent(
                    ticket_id=t.id,
                    rule_id=rng.choice(rules).id,
                    trigger=EscalationTrigger.SLA_BREACH,
                    triggered_at=t.created_at + timedelta(minutes=90),
                    escalated_to_id=supervisor.id if supervisor else None,
                    reason="Resolution SLA exceeded the configured threshold.",
                )
            )
    await session.flush()


async def main() -> None:
    configure_logging()
    # Ensure roles/permissions exist first (reuse the base seeder's logic).
    await base_seed.main()

    async with SessionLocal() as session:
        branches = await _get_or_create_branches(session)
        users = await _get_or_create_users(session, branches)
        tickets = await _seed_tickets(session, users, branches)
        await _seed_comments(session, tickets, users)
        await _seed_sla_tracking(session, tickets)
        await _seed_escalations(session, tickets, users)
        await session.commit()

    log.info(
        "demo_seed_complete",
        branches=len(branches),
        users=len(users),
        tickets=len(tickets),
        password=DEMO_PASSWORD,
    )
    print(
        "\nDemo data ready. Log in with any of these (password: "
        f"{DEMO_PASSWORD}):\n"
        "  admin@successbank.com       (admin)\n"
        "  supervisor@successbank.com  (supervisor)\n"
        "  auditor@successbank.com     (auditor)\n"
        "  agent1..agent5@successbank.com   (agent)\n"
        "  branch1..branch4@successbank.com (branch_user)\n"
    )


if __name__ == "__main__":
    asyncio.run(main())
