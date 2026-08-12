"""Idempotent dev seed — roles, users, categories, SLA policies, and demo tickets.

Run automatically on container startup via docker-compose. Safe to re-run:
skips any entity that already exists.

Seeded logins (all demo users share the same password):
  admin@successbank.local        / Admin@123456    — admin
  super.admin@successbank.local  / Passw0rd@123    — admin + super admin
  priya.sharma@successbank.local / Passw0rd@123    — supervisor
  meera.nair@successbank.local   / Passw0rd@123    — supervisor
  rahul.verma@successbank.local  / Passw0rd@123    — agent
  aisha.khan@successbank.local   / Passw0rd@123    — agent
  vikram.rao@successbank.local   / Passw0rd@123    — agent
  deepak.iyer@successbank.local  / Passw0rd@123    — auditor
  sunita.desai@successbank.local / Passw0rd@123    — branch_user
  arjun.mehta@successbank.local  / Passw0rd@123    — branch_user

Demo tickets are tagged "demo-seed" so re-running this script detects them and
skips re-creation rather than duplicating the whole set.
"""

from __future__ import annotations

import argparse
import asyncio
import random
import sys
import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import settings
from app.core.security import hash_password
from app.models.ai_interaction import AIInteractionLog
from app.models.comment import CommentSource, TicketComment
from app.models.escalation import EscalationEvent, EscalationRule, EscalationTrigger
from app.models.role import Role
from app.models.sla import SLAPolicy, SLATracking
from app.models.ticket import (
    Ticket,
    TicketCategory,
    TicketPriority,
    TicketSource,
    TicketStatus,
    TicketSubCategory,
)
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

# Shared password for every non-admin demo user.
DEMO_PASSWORD = "Passw0rd@123"

# Marks every row this script creates so re-runs can detect and skip them.
DEMO_TAG = "demo-seed"

# (email_local_part, full_name, role, is_super_admin)
DEMO_USERS = [
    # One super admin, distinct from the ordinary admin, so the two privilege
    # tiers can be told apart when testing (only a super admin may grant the
    # super-admin flag or manage another super admin).
    ("super.admin",   "Ravi Deshmukh", "admin",       True),
    ("priya.sharma",  "Priya Sharma",  "supervisor",  False),
    ("meera.nair",    "Meera Nair",    "supervisor",  False),
    ("rahul.verma",   "Rahul Verma",   "agent",       False),
    ("aisha.khan",    "Aisha Khan",    "agent",       False),
    ("vikram.rao",    "Vikram Rao",    "agent",       False),
    ("deepak.iyer",   "Deepak Iyer",   "auditor",     False),
    ("sunita.desai",  "Sunita Desai",  "branch_user", False),
    ("arjun.mehta",   "Arjun Mehta",   "branch_user", False),
]

# (code, name, department, banking_domain, subcategories)
#
# The 0002 migration already seeds the first seven categories along with a
# base set of subcategories — those codes are reproduced verbatim here so the
# two stay in agreement, and the extra subcategories below simply fill gaps.
CATEGORIES = [
    ("payments", "Payments & Transfers", "Payments Operations", "payments", [
        ("neft_rtgs",          "NEFT / RTGS"),
        ("upi_payments",       "UPI Payments"),
        ("card_payments",      "Card Payments"),
    ]),
    ("fraud", "Fraud & Security", "Risk & Compliance", "fraud", [
        ("account_fraud",      "Account Fraud"),
        ("txn_dispute",        "Transaction Dispute"),
    ]),
    ("kyc", "KYC & Onboarding", "Compliance", "kyc", [
        ("kyc_verification",   "KYC Verification"),
        ("onboarding",         "Onboarding"),
    ]),
    ("loans", "Loans & Credit", "Retail Banking", "loans", [
        ("loan_application",   "Loan Application"),
        ("emi_issues",         "EMI Issues"),
    ]),
    ("compliance", "Regulatory & Compliance", "Compliance", "compliance", [
        ("regulatory_compliance", "Regulatory Compliance"),
        ("audit_queries",         "Audit Queries"),
    ]),
    ("it", "IT & Systems", "Information Technology", "it", [
        ("software_issues",    "Software Issues"),
        ("system_access",      "System Access"),
    ]),
    ("operations", "Operations", "Operations", "operations", [
        ("branch_ops",         "Branch Operations"),
        ("cash_management",    "Cash Management"),
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

# Escalation rules (name, trigger, after_minutes, to_role, priority_threshold)
ESCALATION_RULES = [
    ("Critical SLA breach → Supervisor", "sla_breach", 120,  "supervisor", "critical"),
    ("High priority ageing → Supervisor", "sla_breach", 360, "supervisor", "high"),
    ("Fraud detected → Risk lead",        "high_risk",  None, "supervisor", "high"),
    ("Regulatory matter → Compliance",    "regulatory", None, "admin",      None),
    ("Manual escalation → Supervisor",    "manual",     None, "supervisor", None),
]

# ---------------------------------------------------------------------------
# Demo tickets
# ---------------------------------------------------------------------------
# `age_h` is hours before "now" that the ticket was created — this is what
# drives SLA state, so the SLA Monitor and Escalations pages have a realistic
# spread of breached / at-risk / on-time work without hardcoding timestamps.
#
# comments: (author_key, hours_after_creation, body, is_internal, source)
DEMO_TICKETS = [
    {
        "key": "t1",
        "title": "NEFT transfer of ₹4,50,000 debited but not credited to beneficiary",
        "description": (
            "Customer initiated an NEFT transfer of ₹4,50,000 from account ending 8821 to "
            "an ICICI beneficiary at 09:14 IST. The amount was debited and UTR "
            "SBIN325041400921 was generated, but the beneficiary bank confirms no credit. "
            "Customer is a priority banking client and has escalated to the branch manager."
        ),
        "category": "payments", "subcategory": "neft_rtgs",
        "priority": "critical", "status": "escalated", "source": "phone",
        "reporter": "sunita.desai", "assignee": "rahul.verma",
        "age_h": 9,
        "tags": ["neft", "high-value", "priority-customer"],
        "ai_category": "payments", "ai_confidence": 0.94, "ai_risk_score": 0.81,
        "ai_sentiment": "urgent",
        "ai_summary": (
            "High-value NEFT credit failure with a valid UTR. Beneficiary bank shows no "
            "inward credit. Needs an immediate NPCI raise and a hold on reversal."
        ),
        "comments": [
            ("rahul.verma", 1, "Raised query with NPCI referencing UTR SBIN325041400921. Awaiting response.", False, "agent"),
            ("rahul.verma", 3, "Beneficiary bank confirms the inward message was never received. Escalating to Payments Ops.", True, "agent"),
            ("priya.sharma", 6, "Escalated to Payments Ops lead. Customer to be updated every 2 hours until resolved.", True, "agent"),
        ],
        "escalation": ("sla_breach", 6, "priya.sharma", "Critical payment SLA breached with customer funds in limbo."),
    },
    {
        "key": "t2",
        "title": "Suspected card skimming — 6 unauthorised POS debits overnight",
        "description": (
            "Six POS transactions totalling ₹87,400 were posted against debit card ending "
            "4417 between 01:20 and 02:05 IST across three merchants in a city the customer "
            "has not visited. Customer confirms the card is in their possession."
        ),
        "category": "fraud", "subcategory": "txn_dispute",
        "priority": "critical", "status": "in_progress", "source": "phone",
        "reporter": "arjun.mehta", "assignee": "aisha.khan",
        "age_h": 1.5,
        "tags": ["skimming", "card-fraud", "chargeback"],
        "ai_category": "fraud", "ai_confidence": 0.97, "ai_risk_score": 0.93,
        "ai_sentiment": "urgent",
        "ai_summary": (
            "Card-present fraud pattern consistent with skimming: rapid low-value debits "
            "at unfamiliar merchants outside the customer's usual geography."
        ),
        "comments": [
            ("aisha.khan", 0, "Card hot-listed and blocked. Replacement card requested.", False, "agent"),
            ("aisha.khan", 1, "Chargeback initiated for all six transactions. Fraud pattern reported to the risk team.", True, "agent"),
        ],
    },
    {
        "key": "t3",
        "title": "Core banking system slow — teller screens timing out at Andheri branch",
        "description": (
            "Since 10:30 IST, teller terminals at the Andheri East branch are taking 40-60 "
            "seconds per transaction and intermittently timing out. Roughly 20 staff are "
            "affected and the customer queue is building."
        ),
        "category": "it", "subcategory": "software_issues",
        "priority": "critical", "status": "escalated", "source": "portal",
        "reporter": "sunita.desai", "assignee": "vikram.rao",
        "age_h": 5,
        "tags": ["outage", "branch", "core-banking"],
        "ai_category": "it", "ai_confidence": 0.91, "ai_risk_score": 0.76,
        "ai_sentiment": "negative",
        "comments": [
            ("vikram.rao", 1, "Confirmed elevated latency on the branch application server. Infra team engaged.", False, "agent"),
            ("vikram.rao", 2, "Root cause looks like connection-pool exhaustion after this morning's deploy.", True, "agent"),
        ],
        "escalation": ("sla_breach", 3, "meera.nair", "Branch-wide outage exceeded the critical response SLA."),
    },
    {
        "key": "t4",
        "title": "AML alert — structured cash deposits just below reporting threshold",
        "description": (
            "Automated monitoring flagged account 553012xxxx for eleven cash deposits "
            "between ₹48,000 and ₹49,500 over nine working days, totalling ₹5,32,000. "
            "The pattern suggests deliberate structuring to stay under the ₹50,000 "
            "reporting threshold."
        ),
        "category": "compliance", "subcategory": "regulatory_compliance",
        "priority": "high", "status": "escalated", "source": "api",
        "reporter": "admin", "assignee": "aisha.khan",
        "age_h": 30,
        "tags": ["aml", "structuring", "regulatory"],
        "ai_category": "compliance", "ai_confidence": 0.89, "ai_risk_score": 0.88,
        "ai_sentiment": "neutral",
        "ai_summary": "Classic structuring pattern. Requires STR filing assessment within the regulatory window.",
        "comments": [
            ("aisha.khan", 4, "Pulled 12-month transaction history. Deposits are all cash, all at the same branch.", True, "agent"),
            ("meera.nair", 20, "Referred to the compliance team for STR filing assessment.", True, "agent"),
        ],
        "escalation": ("regulatory", 20, "meera.nair", "Potential STR — regulatory timeline applies."),
    },
    {
        "key": "t5",
        "title": "Duplicate UPI debit — customer charged twice for one payment",
        "description": (
            "Customer paid ₹12,300 to a merchant via UPI. The app showed a failure and they "
            "retried, but both attempts were debited. Only one credit reached the merchant."
        ),
        "category": "payments", "subcategory": "upi_payments",
        "priority": "high", "status": "in_progress", "source": "chat",
        "reporter": "arjun.mehta", "assignee": "rahul.verma",
        "age_h": 5.5,
        "tags": ["upi", "duplicate", "refund"],
        "ai_category": "payments", "ai_confidence": 0.92, "ai_risk_score": 0.34,
        "ai_sentiment": "negative",
        "comments": [
            ("rahul.verma", 1, "Confirmed two debits against a single merchant reference. Refund raised for the duplicate leg.", False, "agent"),
        ],
    },
    {
        "key": "t6",
        "title": "KYC re-verification pending — account restricted for 3 days",
        "description": (
            "Customer's account was restricted pending periodic KYC re-verification. They "
            "submitted an updated Aadhaar and address proof three days ago but the account "
            "remains restricted and they cannot access salary credited yesterday."
        ),
        "category": "kyc", "subcategory": "kyc_verification",
        "priority": "high", "status": "assigned", "source": "email",
        "reporter": "sunita.desai", "assignee": "vikram.rao",
        "age_h": 7,
        "tags": ["kyc", "account-restriction"],
        "ai_category": "kyc", "ai_confidence": 0.86, "ai_risk_score": 0.42,
        "ai_sentiment": "negative",
        "email_from": "sunita.desai@successbank.local",
        "comments": [],
    },
    {
        "key": "t7",
        "title": "Home loan EMI debited twice in the same cycle",
        "description": (
            "Loan account HL-2291884 shows two EMI debits of ₹42,750 on the 5th. The customer "
            "requests reversal of the duplicate and confirmation that it will not affect their "
            "credit report."
        ),
        "category": "loans", "subcategory": "emi_issues",
        "priority": "high", "status": "in_progress", "source": "email",
        "reporter": "arjun.mehta", "assignee": "aisha.khan",
        "age_h": 11,
        "tags": ["loan", "emi", "duplicate-debit"],
        "ai_category": "loans", "ai_confidence": 0.90, "ai_risk_score": 0.38,
        "ai_sentiment": "negative",
        "email_from": "arjun.mehta@successbank.local",
        "comments": [
            ("aisha.khan", 2, "Verified duplicate debit in the loan ledger. Reversal requested from loan operations.", False, "agent"),
            ("aisha.khan", 5, "Confirmed with the credit bureau team that no adverse reporting will occur.", True, "agent"),
        ],
    },
    {
        "key": "t8",
        "title": "ATM cash not dispensed but account debited — ₹20,000",
        "description": (
            "Customer attempted a ₹20,000 withdrawal at ATM ID MUM0473. The machine did not "
            "dispense cash but the account was debited. No reversal after 48 hours."
        ),
        "category": "dispute", "subcategory": "dispute.atm",
        "priority": "high", "status": "on_hold", "source": "portal",
        "reporter": "sunita.desai", "assignee": "rahul.verma",
        "age_h": 50,
        "tags": ["atm", "cash-retract", "dispute"],
        "ai_category": "dispute", "ai_confidence": 0.88, "ai_risk_score": 0.45,
        "ai_sentiment": "negative",
        "sla_paused": True,
        "comments": [
            ("rahul.verma", 3, "EJ log requested from the ATM vendor. SLA paused pending third-party response.", True, "agent"),
        ],
    },
    {
        "key": "t9",
        "title": "Phishing emails impersonating SUCCESS Bank reported by customers",
        "description": (
            "Multiple customers report emails from 'security@success-bank-verify.com' asking "
            "them to reconfirm net-banking credentials. At least two customers clicked through "
            "to the fake portal."
        ),
        "category": "fraud", "subcategory": "account_fraud",
        "priority": "high", "status": "in_progress", "source": "email",
        "reporter": "admin", "assignee": "vikram.rao",
        "age_h": 3,
        "tags": ["phishing", "brand-abuse", "security"],
        "ai_category": "fraud", "ai_confidence": 0.95, "ai_risk_score": 0.79,
        "ai_sentiment": "urgent",
        "comments": [
            ("vikram.rao", 1, "Takedown request filed with the registrar. Affected customers' credentials force-reset.", False, "agent"),
        ],
    },
    {
        "key": "t10",
        "title": "Nostro account reconciliation break — USD 14,200 unmatched",
        "description": (
            "The daily nostro reconciliation for the USD correspondent account shows an "
            "unmatched credit of USD 14,200 dated two business days ago with no matching "
            "internal entry."
        ),
        "category": "operations", "subcategory": "branch_ops",
        "priority": "medium", "status": "assigned", "source": "api",
        "reporter": "admin", "assignee": "aisha.khan",
        "age_h": 23.5,
        "tags": ["nostro", "reconciliation", "fx"],
        "ai_category": "operations", "ai_confidence": 0.83, "ai_risk_score": 0.29,
        "ai_sentiment": "neutral",
        "comments": [],
    },
    {
        "key": "t11",
        "title": "Access request — new joiner needs teller module permissions",
        "description": (
            "New joiner Rohit Kulkarni (employee ID 44219) starts Monday at the Powai branch "
            "and needs teller module access plus read access to the customer 360 dashboard."
        ),
        "category": "access", "subcategory": "access.update",
        "priority": "low", "status": "new", "source": "portal",
        "reporter": "sunita.desai", "assignee": None,
        "age_h": 2,
        "tags": ["onboarding", "access-request"],
        "ai_category": "access", "ai_confidence": 0.79, "ai_risk_score": 0.10,
        "ai_sentiment": "neutral",
        "comments": [],
    },
    {
        "key": "t12",
        "title": "Cheque book request not delivered after 15 days",
        "description": (
            "Customer requested a cheque book on the 1st. Tracking shows dispatch but nothing "
            "has been delivered and the courier reference returns no data."
        ),
        "category": "operations", "subcategory": "branch_ops",
        "priority": "low", "status": "new", "source": "chat",
        "reporter": "arjun.mehta", "assignee": None,
        "age_h": 6,
        "tags": ["cheque-book", "delivery"],
        "ai_category": "operations", "ai_confidence": 0.72, "ai_risk_score": 0.08,
        "ai_sentiment": "negative",
        "comments": [],
    },
    {
        "key": "t13",
        "title": "FX rate mismatch on inward remittance booking",
        "description": (
            "An inward remittance of GBP 8,000 was converted at 104.22 but the deal ticket "
            "shows 104.87. The customer is disputing the ₹5,200 difference."
        ),
        "category": "treasury", "subcategory": "tsy.fx",
        "priority": "medium", "status": "acknowledged", "source": "email",
        "reporter": "sunita.desai", "assignee": None,
        "age_h": 3,
        "tags": ["fx", "remittance", "rate-dispute"],
        "ai_category": "treasury", "ai_confidence": 0.81, "ai_risk_score": 0.31,
        "ai_sentiment": "negative",
        "email_from": "sunita.desai@successbank.local",
        "comments": [],
    },
    {
        "key": "t14",
        "title": "Net banking login blocked after password reset",
        "description": (
            "Customer reset their net-banking password successfully but every subsequent login "
            "returns 'profile locked'. Unlocking from the branch terminal has not helped."
        ),
        "category": "access", "subcategory": "access.locked",
        "priority": "medium", "status": "new", "source": "phone",
        "reporter": "arjun.mehta", "assignee": None,
        "age_h": 1,
        "tags": ["net-banking", "account-locked"],
        "ai_category": "access", "ai_confidence": 0.84, "ai_risk_score": 0.15,
        "ai_sentiment": "negative",
        "comments": [],
    },
    {
        "key": "t15",
        "title": "Merchant chargeback representment documents requested",
        "description": (
            "The acquiring bank has requested representment documents for chargeback case "
            "CB-88412 within five working days. The merchant has supplied the delivery proof."
        ),
        "category": "dispute", "subcategory": "dispute.merchant",
        "priority": "medium", "status": "in_progress", "source": "email",
        "reporter": "admin", "assignee": "rahul.verma",
        "age_h": 14,
        "tags": ["chargeback", "representment"],
        "ai_category": "dispute", "ai_confidence": 0.87, "ai_risk_score": 0.22,
        "ai_sentiment": "neutral",
        "comments": [
            ("rahul.verma", 6, "Delivery proof and signed invoice collected from the merchant. Submitting to the acquirer.", False, "agent"),
        ],
    },
    {
        "key": "t16",
        "title": "Standing instruction failed — insurance premium not paid",
        "description": (
            "A standing instruction for a ₹18,500 annual insurance premium failed despite "
            "sufficient balance. The policy is now within its grace period."
        ),
        "category": "payments", "subcategory": "neft_rtgs",
        "priority": "medium", "status": "resolved", "source": "portal",
        "reporter": "sunita.desai", "assignee": "vikram.rao",
        "age_h": 40, "resolved_after_h": 9,
        "tags": ["standing-instruction", "insurance"],
        "ai_category": "payments", "ai_confidence": 0.85, "ai_risk_score": 0.18,
        "ai_sentiment": "neutral",
        "comments": [
            ("vikram.rao", 2, "SI had lapsed because the mandate expiry was not renewed. Mandate re-registered.", False, "agent"),
            ("vikram.rao", 9, "Premium paid manually and confirmed with the insurer. Customer notified.", False, "agent"),
        ],
    },
    {
        "key": "t17",
        "title": "Loan closure certificate not issued after full prepayment",
        "description": (
            "Customer prepaid personal loan PL-771204 in full three weeks ago but has not "
            "received the closure certificate or the no-dues letter needed for their next loan."
        ),
        "category": "loans", "subcategory": "loan_application",
        "priority": "medium", "status": "resolved", "source": "email",
        "reporter": "arjun.mehta", "assignee": "aisha.khan",
        "age_h": 72, "resolved_after_h": 20,
        "tags": ["loan-closure", "documentation"],
        "ai_category": "loans", "ai_confidence": 0.88, "ai_risk_score": 0.12,
        "ai_sentiment": "negative",
        "comments": [
            ("aisha.khan", 18, "Closure certificate and no-dues letter issued and emailed to the customer.", False, "agent"),
        ],
    },
    {
        "key": "t18",
        "title": "Statement download failing for accounts with over 500 transactions",
        "description": (
            "Customers with high transaction volumes get a 504 when downloading a 12-month PDF "
            "statement. CSV export works. Reproducible on two accounts."
        ),
        "category": "it", "subcategory": "software_issues",
        "priority": "medium", "status": "resolved", "source": "portal",
        "reporter": "sunita.desai", "assignee": "vikram.rao",
        "age_h": 60, "resolved_after_h": 26,
        "tags": ["bug", "statements", "timeout"],
        "ai_category": "it", "ai_confidence": 0.90, "ai_risk_score": 0.20,
        "ai_sentiment": "neutral",
        "comments": [
            ("vikram.rao", 20, "PDF renderer was loading all rows into memory. Switched to streaming pagination.", True, "agent"),
            ("vikram.rao", 26, "Fix deployed. Verified against both reported accounts.", False, "agent"),
        ],
    },
    {
        "key": "t19",
        "title": "Address update request with supporting documents",
        "description": (
            "Customer moved cities and submitted a rental agreement plus a utility bill to "
            "update their registered address across all linked accounts."
        ),
        "category": "kyc", "subcategory": "kyc_verification",
        "priority": "low", "status": "closed", "source": "portal",
        "reporter": "arjun.mehta", "assignee": "rahul.verma",
        "age_h": 120, "resolved_after_h": 30, "closed_after_h": 48,
        "tags": ["address-update", "kyc"],
        "ai_category": "kyc", "ai_confidence": 0.93, "ai_risk_score": 0.05,
        "ai_sentiment": "positive",
        "comments": [
            ("rahul.verma", 28, "Documents verified against the KYC checklist. Address updated on all four linked accounts.", False, "agent"),
        ],
    },
    {
        "key": "t20",
        "title": "Internal audit query — dormant account reactivation approvals",
        "description": (
            "Internal audit requests the approval trail for 14 dormant accounts reactivated "
            "last quarter, including maker-checker evidence for each."
        ),
        "category": "compliance", "subcategory": "audit_queries",
        "priority": "low", "status": "closed", "source": "api",
        "reporter": "admin", "assignee": "aisha.khan",
        "age_h": 200, "resolved_after_h": 60, "closed_after_h": 90,
        "tags": ["audit", "dormant-accounts"],
        "ai_category": "compliance", "ai_confidence": 0.80, "ai_risk_score": 0.11,
        "ai_sentiment": "neutral",
        "comments": [
            ("aisha.khan", 50, "Compiled maker-checker evidence for all 14 accounts and shared via the audit portal.", True, "agent"),
        ],
    },
    {
        "key": "t21",
        "title": "Reopened: salary credit still not reflected after KYC unblock",
        "description": (
            "Originally reported as resolved, but the customer confirms the salary credit is "
            "still not visible even though the account restriction was lifted."
        ),
        "category": "payments", "subcategory": "neft_rtgs",
        "priority": "high", "status": "reopened", "source": "phone",
        "reporter": "sunita.desai", "assignee": "rahul.verma",
        "age_h": 26, "reopen_count": 1,
        "tags": ["salary-credit", "reopened"],
        "ai_category": "payments", "ai_confidence": 0.87, "ai_risk_score": 0.52,
        "ai_sentiment": "negative",
        "comments": [
            ("rahul.verma", 4, "Marked resolved after the restriction was lifted.", False, "agent"),
            ("sunita.desai", 24, "Customer called back — credit still not visible. Reopening.", False, "agent"),
        ],
    },
]


# ---------------------------------------------------------------------------
# Generated backlog
# ---------------------------------------------------------------------------
# The 21 tickets above are hand-written so the app has believable narratives to
# read. They all sit within the last few days though, which leaves the trend
# chart with almost no curve and "resolved today" reading zero. This generator
# fills in a further ~35 tickets stretching back six weeks, weighted so older
# work is mostly finished and recent work is mostly open — the shape a real
# queue has.
#
# Seeded RNG: re-running produces byte-identical data, so screenshots and bug
# reports stay reproducible.

_BACKLOG_TEMPLATES: list[tuple[str, str, str, str]] = [
    # (category, subcategory, title, description)
    ("payments", "neft_rtgs", "RTGS transfer pending beyond cut-off",
     "A same-day RTGS instruction for ₹12,00,000 was accepted before cut-off but is still showing as pending with the clearing house."),
    ("payments", "upi_payments", "UPI mandate failing for recurring SIP",
     "The customer's monthly SIP mandate declines every cycle even though the balance is sufficient."),
    ("payments", "card_payments", "Card payment declined at international merchant",
     "International usage is enabled but transactions at a specific merchant category keep declining."),
    ("fraud", "account_fraud", "Unrecognised beneficiary added to net banking",
     "A beneficiary the customer does not recognise was added and a transfer attempted within minutes."),
    ("fraud", "txn_dispute", "Disputed contactless transactions after card loss",
     "Four contactless debits posted after the customer reported the card lost."),
    ("kyc", "kyc_verification", "Periodic KYC refresh overdue for corporate account",
     "The corporate account is past its periodic KYC refresh date and transactions are about to be restricted."),
    ("kyc", "onboarding", "New account opening stuck at video KYC step",
     "The applicant completed document upload but the video KYC session fails to launch on Android."),
    ("loans", "emi_issues", "EMI bounce charge applied despite sufficient balance",
     "The account held the full EMI amount on the due date but the mandate still bounced and a charge was levied."),
    ("loans", "loan_application", "Loan sanction letter not received after approval",
     "The application shows approved in the portal but no sanction letter has been issued."),
    ("compliance", "regulatory_compliance", "CTR threshold breach needs review",
     "Aggregate cash transactions on the account crossed the CTR reporting threshold this month."),
    ("compliance", "audit_queries", "Branch audit query on cash retention limits",
     "Internal audit has asked for an explanation of overnight cash retention above the branch limit."),
    ("it", "software_issues", "Statement PDF renders blank for joint accounts",
     "Downloaded statements are blank for joint accounts; single-holder accounts are unaffected."),
    ("it", "system_access", "Branch printer queue offline after network change",
     "Cheque and passbook printers at the branch stopped responding after last night's network maintenance."),
    ("operations", "branch_ops", "Cash remittance mismatch at end of day",
     "The branch cash remittance to the currency chest is short by ₹4,500 against the system figure."),
    ("operations", "cash_management", "ATM cash-out during weekend peak",
     "The lobby ATM ran dry on Saturday afternoon and was not replenished until Monday."),
    ("treasury", "tsy.liquidity", "Intraday liquidity buffer below threshold",
     "The intraday liquidity buffer dipped below the internal floor twice this week."),
    ("dispute", "dispute.chargeback", "Chargeback deadline approaching for e-commerce dispute",
     "The representment window for a ₹34,000 e-commerce dispute closes in three working days."),
    ("access", "access.reset", "Bulk password reset needed after training session",
     "Twelve new joiners need their net-banking demo credentials reset after a training session."),
    ("access", "access.locked", "Corporate user locked out of payment portal",
     "The maker at a corporate client is locked out and payroll runs tomorrow."),
    ("payments", "neft_rtgs", "Inward remittance credited to wrong account",
     "An inward NEFT was credited to a closed account and needs to be traced and re-credited."),
]

_BACKLOG_TAGS = {
    "payments": ["payments", "transfers"],
    "fraud": ["fraud", "risk"],
    "kyc": ["kyc", "onboarding"],
    "loans": ["loans"],
    "compliance": ["compliance", "regulatory"],
    "it": ["it", "systems"],
    "operations": ["operations"],
    "treasury": ["treasury"],
    "dispute": ["dispute"],
    "access": ["access"],
}

_AGENT_KEYS = ["rahul.verma", "aisha.khan", "vikram.rao"]
_REPORTER_KEYS = ["sunita.desai", "arjun.mehta", "admin"]
_SENTIMENTS = ["neutral", "negative", "urgent", "positive"]

#: Resolution targets in hours, mirroring SLA_DEFAULTS above.
_SLA_RESOLUTION_HOURS = {p: res / 60 for p, _resp, res in SLA_DEFAULTS}


def _generate_backlog(count: int = 35) -> list[dict]:
    """Build the older half of the queue, oldest mostly closed."""
    rng = random.Random(20260810)  # fixed: reruns reproduce the same backlog
    specs: list[dict] = []

    for i in range(count):
        category, subcategory, title, description = _BACKLOG_TEMPLATES[i % len(_BACKLOG_TEMPLATES)]

        # Spread across six weeks, densest in the recent past.
        age_h = round(rng.triangular(3, 45 * 24, 24), 1)
        days_old = age_h / 24

        # Older work has had time to finish. This weighting matters more than
        # it looks: an old ticket left open is a guaranteed breach, so leaning
        # too far toward "still open" produces a queue with a 75% breach rate
        # and an SLA panel nobody would believe.
        if days_old > 10:
            status = rng.choice(["closed", "closed", "closed", "resolved"])
        elif days_old > 3:
            status = rng.choices(
                ["closed", "resolved", "on_hold"], weights=[45, 45, 10]
            )[0]
        elif days_old > 1:
            status = rng.choice(["in_progress", "assigned", "escalated", "resolved"])
        else:
            status = rng.choice(["new", "acknowledged", "assigned", "in_progress"])

        priority = rng.choices(
            ["critical", "high", "medium", "low"], weights=[6, 24, 45, 25]
        )[0]

        assignee = None if status in {"new", "acknowledged"} else rng.choice(_AGENT_KEYS)

        spec: dict = {
            "key": f"b{i}",
            "title": title,
            "description": description,
            "category": category,
            "subcategory": subcategory,
            "priority": priority,
            "status": status,
            "source": rng.choice(["portal", "email", "phone", "chat", "api"]),
            "reporter": rng.choice(_REPORTER_KEYS),
            "assignee": assignee,
            "age_h": age_h,
            "tags": _BACKLOG_TAGS[category],
            "ai_category": category,
            "ai_confidence": round(rng.uniform(0.71, 0.97), 2),
            "ai_risk_score": round(rng.uniform(0.05, 0.65), 2),
            "ai_sentiment": rng.choice(_SENTIMENTS),
            "comments": [],
        }

        # An on-hold ticket has its clock paused, which is how a genuinely
        # stalled item avoids counting as a breach.
        if status == "on_hold":
            spec["sla_paused"] = True

        if status in {"resolved", "closed"}:
            # Resolution time is measured against the SLA target, not against
            # the ticket's age: finishing "70% of the way through its life" is
            # meaningless for a three-week-old ticket and breaches every time.
            # About one in five misses, which is the shape of a real queue.
            sla_hours = _SLA_RESOLUTION_HOURS[priority]
            if rng.random() < 0.8:
                resolved_after = round(rng.uniform(0.15, 0.85) * sla_hours, 1)
            else:
                resolved_after = round(rng.uniform(1.15, 2.4) * sla_hours, 1)
            resolved_after = max(0.4, min(resolved_after, age_h))

            # Push a few over the line today so "Resolved today" is not zero.
            if i % 6 == 0:
                resolved_after = max(0.4, age_h - rng.uniform(0.5, 5))

            spec["resolved_after_h"] = resolved_after
            if status == "closed":
                spec["closed_after_h"] = min(age_h, resolved_after + rng.uniform(1, 20))

        specs.append(spec)

    return specs


DEMO_TICKETS += _generate_backlog()


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
    # The 0002 migration seeds most categories, so this pass has to be additive
    # at the subcategory level too — otherwise a category that already exists
    # silently keeps whatever gaps it shipped with.
    existing_cats = {
        c.code: c
        for c in (await db.execute(select(TicketCategory))).scalars().all()
    }
    existing_subs = {
        s.code
        for s in (await db.execute(select(TicketSubCategory))).scalars().all()
    }
    created_cats: list[str] = []
    created_subs: list[str] = []

    for code, name, department, banking_domain, subcats in CATEGORIES:
        cat = existing_cats.get(code)
        if cat is None:
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
            existing_cats[code] = cat
            created_cats.append(code)

        for sub_code, sub_name in subcats:
            if sub_code in existing_subs:
                continue
            db.add(TicketSubCategory(
                id=uuid.uuid4(),
                category_id=cat.id,
                code=sub_code,
                name=sub_name,
                description=sub_name,
                is_active=True,
            ))
            existing_subs.add(sub_code)
            created_subs.append(sub_code)

    if created_cats or created_subs:
        await db.flush()
        print(
            f"  [seed] Categories: +{len(created_cats)} "
            f"({', '.join(created_cats) or 'none'}), "
            f"subcategories: +{len(created_subs)}"
        )
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

    # --- Demo users ----------------------------------------------------------
    await seed_demo_users(db)

    # --- Escalation rules ----------------------------------------------------
    await seed_escalation_rules(db)

    # --- Demo tickets, comments, escalation events ---------------------------
    await seed_demo_tickets(db)

    # --- Ticket attachments (needs the tickets and comments above) ----------
    await seed_attachments(db)

    # --- Branch network -----------------------------------------------------
    await seed_branches(db)
    await assign_tickets_to_branches(db)

    # --- AI interaction history (drives the dashboard's AI panel) ------------
    await seed_ai_interaction_logs(db)

    await db.commit()


async def seed_demo_users(db: AsyncSession) -> None:
    """Create one user per demo persona, covering every role."""
    roles = {r.name: r for r in (await db.execute(select(Role))).scalars().all()}
    existing_emails = {
        e for e in (await db.execute(select(User.email))).scalars().all()
    }

    created: list[str] = []
    # Hashing is deliberately slow — do it once and reuse for every demo user.
    demo_hash = hash_password(DEMO_PASSWORD)

    for local_part, full_name, role_name, is_super in DEMO_USERS:
        email = f"{local_part}@successbank.local"
        if email in existing_emails:
            continue
        role = roles.get(role_name)
        if role is None:
            print(f"  [seed] WARNING: role {role_name!r} missing — skipping {email}")
            continue
        db.add(User(
            id=uuid.uuid4(),
            email=email,
            full_name=full_name,
            password_hash=demo_hash,
            role_id=role.id,
            is_super_admin=is_super,
            is_active=True,
        ))
        created.append(f"{email} ({role_name}{', super admin' if is_super else ''})")

    if created:
        await db.flush()
        print(f"  [seed] Created {len(created)} demo users (password: {DEMO_PASSWORD}):")
        for line in created:
            print(f"           - {line}")
    else:
        print("  [seed] Demo users already exist — skipped")


async def seed_escalation_rules(db: AsyncSession) -> None:
    """Create the default escalation rules used by the Escalations page."""
    existing = {
        r.name for r in (await db.execute(select(EscalationRule))).scalars().all()
    }
    created: list[str] = []
    for name, trigger, after_min, to_role, threshold in ESCALATION_RULES:
        if name in existing:
            continue
        db.add(EscalationRule(
            id=uuid.uuid4(),
            name=name,
            trigger=EscalationTrigger(trigger),
            trigger_after_minutes=after_min,
            escalate_to_role=to_role,
            priority_threshold=threshold,
            notify_email="manager@successbank.local",
            is_active=True,
        ))
        created.append(name)

    if created:
        await db.flush()
        print(f"  [seed] Created {len(created)} escalation rules")
    else:
        print("  [seed] Escalation rules already exist — skipped")


async def seed_demo_tickets(db: AsyncSession) -> None:
    """Create the demo ticket set with comments and escalation events.

    Ticket timestamps are computed backwards from "now" so SLA state is always
    fresh: the same seed produces breached, at-risk, and on-time tickets no
    matter when it runs.
    """
    # Idempotency: any ticket carrying DEMO_TAG means the set is already loaded.
    already = (await db.execute(
        select(Ticket.id).where(Ticket.tags.any(DEMO_TAG)).limit(1)
    )).first()
    if already is not None:
        print("  [seed] Demo tickets already exist — skipped")
        return

    users = {
        u.email.split("@")[0]: u
        for u in (await db.execute(select(User))).scalars().all()
    }
    categories = {
        c.code: c for c in (await db.execute(select(TicketCategory))).scalars().all()
    }
    subcategories = {
        s.code: s
        for s in (await db.execute(select(TicketSubCategory))).scalars().all()
    }
    policies = {
        p.priority: p
        for p in (await db.execute(
            select(SLAPolicy).where(SLAPolicy.is_default.is_(True))
        )).scalars().all()
    }
    rules = {
        r.trigger: r
        for r in (await db.execute(select(EscalationRule))).scalars().all()
    }
    sla_minutes = {p: (resp, res) for p, resp, res in SLA_DEFAULTS}

    now = datetime.now(UTC)
    counters: dict[str, int] = {}
    ticket_ids: dict[str, uuid.UUID] = {}
    # (spec, ticket_id, created_at, assignee) — filled in pass 1, drained in pass 2
    pending_children: list[tuple[dict, uuid.UUID, datetime, User | None]] = []
    tracking_rows: list[dict] = []
    breached_count = 0
    escalation_count = 0
    comment_count = 0

    for spec in DEMO_TICKETS:
        reporter = users.get(spec["reporter"])
        if reporter is None:
            print(f"  [seed] WARNING: reporter {spec['reporter']!r} missing — skipping {spec['key']}")
            continue
        assignee = users.get(spec["assignee"]) if spec.get("assignee") else None

        created_at = now - timedelta(hours=spec["age_h"])

        # Match the format the application itself generates for users without
        # an org unit (`TKT-000123`). The seed previously used a date-stamped
        # scheme of its own, so demo tickets and anything raised through the UI
        # looked like they came from two different systems.
        counters["seq"] = counters.get("seq", 0) + 1
        ticket_number = f"TKT-{counters['seq']:06d}"

        priority = spec["priority"]
        resp_min, res_min = sla_minutes[priority]
        response_due_at   = created_at + timedelta(minutes=resp_min)
        resolution_due_at = created_at + timedelta(minutes=res_min)

        status = TicketStatus(spec["status"])
        is_done = status in {TicketStatus.RESOLVED, TicketStatus.CLOSED}

        resolved_at = None
        closed_at = None
        if spec.get("resolved_after_h") is not None:
            resolved_at = created_at + timedelta(hours=spec["resolved_after_h"])
        if spec.get("closed_after_h") is not None:
            closed_at = created_at + timedelta(hours=spec["closed_after_h"])

        # First response lands shortly after the first agent comment, if any.
        first_response_at = None
        if spec["comments"]:
            first_response_at = created_at + timedelta(hours=spec["comments"][0][1])
        elif assignee is not None:
            first_response_at = created_at + timedelta(minutes=resp_min // 2)

        # SLA is breached when resolution ran past its due time — measured at
        # resolution for finished tickets, and against "now" for open ones.
        sla_paused_at = created_at + timedelta(hours=3) if spec.get("sla_paused") else None
        if is_done:
            sla_breached = bool(resolved_at and resolved_at > resolution_due_at)
        elif sla_paused_at is not None:
            sla_breached = False  # clock stopped — never counts as breached
        else:
            sla_breached = now > resolution_due_at
        breached_count += int(sla_breached)

        category = categories.get(spec["category"])
        subcategory = subcategories.get(spec.get("subcategory") or "")
        policy = policies.get(priority)

        ticket = Ticket(
            id=uuid.uuid4(),
            ticket_number=ticket_number,
            title=spec["title"],
            description=spec["description"],
            status=status,
            priority=TicketPriority(priority),
            source=TicketSource(spec["source"]),
            category_id=category.id if category else None,
            subcategory_id=subcategory.id if subcategory else None,
            department=category.department if category else None,
            reporter_id=reporter.id,
            assignee_id=assignee.id if assignee else None,
            reopen_count=spec.get("reopen_count", 0),
            tags=[*spec.get("tags", []), DEMO_TAG],
            ai_category=spec.get("ai_category"),
            ai_subcategory=spec.get("subcategory"),
            ai_confidence=spec.get("ai_confidence"),
            ai_summary=spec.get("ai_summary"),
            ai_risk_score=spec.get("ai_risk_score"),
            ai_sentiment=spec.get("ai_sentiment"),
            email_from=spec.get("email_from"),
            sla_policy_id=policy.id if policy else None,
            response_due_at=response_due_at,
            resolution_due_at=resolution_due_at,
            sla_breached=sla_breached,
            sla_paused_at=sla_paused_at,
            first_response_at=first_response_at,
            resolved_at=resolved_at,
            closed_at=closed_at,
            created_at=created_at,
            updated_at=closed_at or resolved_at or now,
        )
        db.add(ticket)
        ticket_ids[spec["key"]] = ticket.id
        pending_children.append((spec, ticket.id, created_at, assignee))

        # The dashboard's SLA panel counts sla_tracking rows, not Ticket
        # columns — without this the SLA Monitor would report 100% compliance
        # while the ticket table under it listed breached tickets.
        tracking_rows.append(dict(
            ticket_id=ticket.id,
            policy_id=policy.id if policy else None,
            response_due_at=response_due_at,
            resolution_due_at=resolution_due_at,
            first_response_at=first_response_at,
            resolved_at=resolved_at,
            is_response_breached=bool(
                first_response_at is None
                and sla_paused_at is None
                and now > response_due_at
            ) or bool(first_response_at and first_response_at > response_due_at),
            is_resolution_breached=sla_breached,
            paused_at=sla_paused_at,
        ))

    # Tickets must hit the database before their comments and escalation
    # events: the FK graph has a cycle (users ↔ org_units), so SQLAlchemy's
    # topological sort can't reliably order the child inserts after the parent.
    await db.flush()

    for row in tracking_rows:
        db.add(SLATracking(id=uuid.uuid4(), **row))

    for spec, ticket_id, created_at, assignee in pending_children:
        for author_key, hours_after, body, is_internal, source in spec["comments"]:
            author = users.get(author_key)
            db.add(TicketComment(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                author_id=author.id if author else None,
                body=body,
                is_internal=is_internal,
                source=CommentSource(source),
                ai_generated=False,
                created_at=created_at + timedelta(hours=hours_after),
                updated_at=created_at + timedelta(hours=hours_after),
            ))
            comment_count += 1

        escalation = spec.get("escalation")
        if escalation:
            trigger, hours_after, to_key, reason = escalation
            trigger_enum = EscalationTrigger(trigger)
            escalated_to = users.get(to_key)
            db.add(EscalationEvent(
                id=uuid.uuid4(),
                ticket_id=ticket_id,
                rule_id=rules[trigger_enum].id if trigger_enum in rules else None,
                trigger=trigger_enum,
                triggered_at=created_at + timedelta(hours=hours_after),
                escalated_to_id=escalated_to.id if escalated_to else None,
                escalated_by_id=assignee.id if assignee else None,
                reason=reason,
            ))
            escalation_count += 1

    await db.flush()
    print(
        f"  [seed] Created {len(ticket_ids)} demo tickets "
        f"({breached_count} SLA-breached), {len(tracking_rows)} SLA tracking rows, "
        f"{comment_count} comments, {escalation_count} escalation events"
    )



# (code, name, region, status, capacity, note)
#
# A believable Maharashtra network: mostly operational, with a couple of
# branches degraded so the Branch Management screen has something to show
# besides a wall of green.
BRANCHES = [
    ("MH-001", "Mumbai HQ",         "Mumbai Metro", "operational", 30, ""),
    ("PU-002", "Pune Central",      "Pune",         "operational", 20, ""),
    ("NK-003", "Nashik",            "North Maharashtra", "maintenance", 12,
     "Scheduled core-banking upgrade until 18:00"),
    ("AU-004", "Aurangabad",        "Marathwada",   "operational", 12, ""),
    ("NG-005", "Nagpur",            "Vidarbha",     "incident",    16,
     "Lobby ATM offline since 06:00"),
    ("TN-006", "Thane",             "Mumbai Metro", "operational", 18, ""),
    ("KL-007", "Kolhapur",          "Western Maharashtra", "operational", 10, ""),
    ("SL-008", "Solapur",           "Western Maharashtra", "maintenance", 10,
     "Power maintenance, generator in use"),
    ("NM-009", "Navi Mumbai",       "Mumbai Metro", "operational", 18, ""),
    ("BO-010", "Borivali",          "Mumbai Metro", "operational", 14, ""),
    ("AN-011", "Andheri East",      "Mumbai Metro", "operational", 22, ""),
    ("PI-012", "Pimpri-Chinchwad",  "Pune",         "operational", 14, ""),
]


#: Small but genuinely valid files, so a demo download opens in a real viewer
#: rather than producing a corrupt-file warning. Each is a complete document of
#: its type — a 1x1 PNG, a minimal one-page PDF, and plain CSV.
_PNG_1PX = bytes.fromhex(
    "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
    "890000000a49444154789c6360000002000100fdff03fa0000000049454e44ae426082"
)

_MINIMAL_PDF = (
    b"%PDF-1.4\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
    b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
    b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 100]>>endobj\n"
    b"trailer<</Root 1 0 R>>\n"
    b"%%EOF\n"
)

_DISPUTE_CSV = (
    b"date,description,amount,channel\n"
    b"2026-08-09,POS PURCHASE 4417,12400.00,card\n"
    b"2026-08-09,POS PURCHASE 4417,12400.00,card\n"
    b"2026-08-10,REVERSAL 4417,-12400.00,card\n"
)


async def seed_attachments(db: AsyncSession) -> None:
    """Put real files on a few demo tickets, and one on an agent's reply.

    Uploads the bytes to object storage rather than only writing rows: an
    Attachment whose `s3_key` points at nothing looks fine in the list and
    fails on download, which is a worse demo than having no attachments.

    Skipped with an explanation if storage is unreachable — seeding must not
    fail because MinIO happens to be down.
    """
    from sqlalchemy import select

    from app.models.attachment import Attachment
    from app.models.comment import TicketComment
    from app.models.ticket import Ticket
    from app.services.storage_service import build_key, storage

    existing = (await db.execute(select(Attachment).limit(1))).scalar_one_or_none()
    if existing is not None:
        print("  [seed] Attachments already exist — skipped")
        return

    try:
        await storage.ensure_bucket()
    except Exception as exc:  # storage is optional for a demo
        print(f"  [seed] Object storage unavailable, skipping attachments ({exc})")
        return

    tickets = list((await db.execute(
        select(Ticket).where(Ticket.tags.any(DEMO_TAG)).order_by(Ticket.created_at.desc()).limit(6)
    )).scalars().all())
    if not tickets:
        print("  [seed] No demo tickets to attach files to — skipped")
        return

    files = [
        ("screenshot_error.png", _PNG_1PX, "image/png"),
        ("account_statement.pdf", _MINIMAL_PDF, "application/pdf"),
        ("disputed_transactions.csv", _DISPUTE_CSV, "text/csv"),
    ]

    created = 0
    on_replies = 0

    for index, ticket in enumerate(tickets):
        # Evidence from the person who raised it — one or two files per ticket.
        for name, payload, content_type in files[: 1 + (index % 3)]:
            extension = name.rsplit(".", 1)[-1]
            try:
                stored = await storage.upload(build_key(ticket.id, extension), payload, content_type)
            except Exception as exc:  # see docstring
                print(f"  [seed] Upload failed, skipping attachments ({exc})")
                return
            db.add(Attachment(
                ticket_id=ticket.id,
                uploader_id=ticket.reporter_id,
                original_filename=name,
                content_type=content_type,
                size_bytes=stored.size_bytes,
                s3_key=stored.key,
                s3_bucket=stored.bucket,
                checksum_sha256=stored.checksum_sha256,
            ))
            created += 1

        # And a fix attached to an agent's public reply, so the ticket page
        # shows the answer and its file together.
        reply = (await db.execute(
            select(TicketComment)
            .where(
                TicketComment.ticket_id == ticket.id,
                TicketComment.is_internal.is_(False),
                TicketComment.author_id.is_not(None),
                TicketComment.author_id != ticket.reporter_id,
            )
            .order_by(TicketComment.created_at.desc())
            .limit(1)
        )).scalar_one_or_none()
        if reply is None:
            continue

        try:
            stored = await storage.upload(
                build_key(ticket.id, "pdf"), _MINIMAL_PDF, "application/pdf"
            )
        except Exception as exc:  # see docstring
            print(f"  [seed] Upload failed, skipping reply attachments ({exc})")
            break
        db.add(Attachment(
            ticket_id=ticket.id,
            comment_id=reply.id,
            uploader_id=reply.author_id,
            original_filename="corrected_statement.pdf",
            content_type="application/pdf",
            size_bytes=stored.size_bytes,
            s3_key=stored.key,
            s3_bucket=stored.bucket,
            checksum_sha256=stored.checksum_sha256,
        ))
        created += 1
        on_replies += 1

    await db.flush()
    print(
        f"  [seed] Created {created} attachments across {len(tickets)} tickets "
        f"({on_replies} attached to an agent's reply)"
    )


async def seed_branches(db: AsyncSession) -> None:
    """Create the branch network and give each one a manager."""
    from app.models.branch import Branch, BranchStatus

    existing = {
        b.code for b in (await db.execute(select(Branch))).scalars().all()
    }
    # Supervisors and admins run branches; agents work tickets at them.
    managers = [
        u for u in (await db.execute(select(User))).scalars().all()
        if u.role and u.role.name in ("supervisor", "admin")
    ]

    created = 0
    for index, (code, name, region, status, capacity, note) in enumerate(BRANCHES):
        if code in existing:
            continue
        db.add(Branch(
            id=uuid.uuid4(),
            code=code,
            name=name,
            region=region,
            address=f"{name} Branch, {region}, Maharashtra",
            ifsc=f"SUCC0{code.replace('-', '')}",
            contact_email=f"{code.lower()}@successbank.local",
            contact_phone=f"+91 22 {4000 + index:04d} {1000 + index:04d}",
            status=BranchStatus(status),
            status_note=note,
            ticket_capacity=capacity,
            manager_id=managers[index % len(managers)].id if managers else None,
            is_active=True,
        ))
        created += 1

    if created:
        await db.flush()
        print(f"  [seed] Created {created} branches")
    else:
        print("  [seed] Branches already exist — skipped")


async def assign_tickets_to_branches(db: AsyncSession) -> None:
    """Spread the demo tickets across the network.

    Without this every branch reads zero open tickets and the load bars are
    all empty, which makes the whole screen look broken rather than idle.
    """
    from app.models.branch import Branch

    branches = (await db.execute(
        select(Branch).where(Branch.is_active.is_(True)).order_by(Branch.code)
    )).scalars().all()
    if not branches:
        return

    tickets = (await db.execute(
        select(Ticket).where(Ticket.tags.any(DEMO_TAG), Ticket.branch_id.is_(None))
    )).scalars().all()
    if not tickets:
        print("  [seed] Tickets already attached to branches — skipped")
        return

    # Weighted so the bigger branches carry more, matching their capacity.
    rng = random.Random(77)
    weights = [b.ticket_capacity for b in branches]
    for ticket in tickets:
        ticket.branch_id = rng.choices(branches, weights=weights)[0].id

    await db.flush()
    print(f"  [seed] Attached {len(tickets)} tickets to branches")


async def seed_ai_interaction_logs(db: AsyncSession) -> None:
    """Populate ai_interaction_logs so the AI panel reports something real.

    The dashboard's AI card reads this table, not the tickets: "Categorized"
    counts rows of type `categorize`, and "Avg confidence" averages their
    confidence_score. The seed never wrote any, so both showed zero while the
    tickets themselves carried perfectly good AI fields.

    Average latency was worse than useless — it averaged whatever real calls
    had happened, which on a machine where Ollama was misconfigured meant
    120-second timeouts and a headline figure of 107,430ms. These rows are
    stamped with the latencies a working local model actually produces.
    """
    existing = (await db.execute(
        select(AIInteractionLog.id)
        .where(AIInteractionLog.model_id.like("seed:%"))
        .limit(1)
    )).first()
    if existing is not None:
        print("  [seed] AI interaction logs already exist — skipped")
        return

    tickets = (await db.execute(
        select(Ticket).where(Ticket.tags.any(DEMO_TAG))
    )).scalars().all()
    if not tickets:
        print("  [seed] No demo tickets — skipping AI logs")
        return

    users = {
        u.email.split("@")[0]: u
        for u in (await db.execute(select(User))).scalars().all()
    }
    actors = [users[k] for k in ("rahul.verma", "aisha.khan", "vikram.rao", "priya.sharma") if k in users]
    if not actors:
        actors = list(users.values())[:1]

    rng = random.Random(4242)
    model = f"seed:{settings.LLM_MODEL}"
    now = datetime.now(UTC)
    created = 0

    def add(ticket, kind, when, *, confidence=None, ok=True, latency=None):
        nonlocal created
        # Latency bands reflect a warm local 9B model: a short classification
        # is quick, a summary costs more, a chat turn most of all.
        base = {"categorize": (700, 2200), "summarize": (1500, 4200),
                "suggest_resolution": (1800, 5200), "chat": (900, 6000)}[kind]
        db.add(AIInteractionLog(
            id=uuid.uuid4(),
            user_id=rng.choice(actors).id,
            ticket_id=ticket.id if ticket is not None else None,
            interaction_type=kind,
            model_id=model,
            prompt_tokens=rng.randint(320, 1400),
            completion_tokens=rng.randint(60, 420),
            latency_ms=latency if latency is not None else rng.randint(*base),
            success=ok,
            error_message=None if ok else "Ollama timed out",
            confidence_score=confidence,
            result={"seeded": True},
            created_at=when,
            updated_at=when,
        ))
        created += 1

    for ticket in tickets:
        start = ticket.created_at

        # Every ticket is classified on arrival — that is the AI step the
        # dashboard counts, and the ticket already carries the confidence the
        # classifier produced, so reuse it rather than inventing a second one.
        add(ticket, "categorize", start + timedelta(seconds=rng.randint(2, 20)),
            confidence=ticket.ai_confidence or round(rng.uniform(0.72, 0.95), 2))

        if ticket.ai_summary:
            add(ticket, "summarize", start + timedelta(minutes=rng.randint(5, 90)))
        if rng.random() < 0.35:
            add(ticket, "suggest_resolution", start + timedelta(minutes=rng.randint(10, 240)))
        if rng.random() < 0.25:
            add(ticket, "chat", start + timedelta(minutes=rng.randint(15, 300)))

    # A couple of genuine failures, so the panel is not implausibly perfect and
    # the failure counter on /ai/usage has something to show.
    for _ in range(3):
        add(None, "chat", now - timedelta(hours=rng.randint(1, 60)),
            ok=False, latency=rng.randint(30_000, 60_000))

    await db.flush()
    print(f"  [seed] Created {created} AI interaction logs")

async def _delete_demo_objects(db: AsyncSession, ticket_ids: list) -> int:
    """Remove the stored bytes for the attachments about to be deleted.

    Reads the keys from the rows first, because once the rows are gone nothing
    records which objects belonged to demo tickets and they can never be found
    again. Storage being unavailable is not fatal — the reset should still
    clear the database — but it is reported, since the objects are then
    genuinely orphaned.
    """
    if not ticket_ids:
        return 0

    from app.models.attachment import Attachment
    from app.services.storage_service import storage

    keys = (await db.execute(
        select(Attachment.s3_key).where(Attachment.ticket_id.in_(ticket_ids))
    )).scalars().all()
    if not keys:
        return 0

    removed = 0
    for key in keys:
        try:
            await storage.delete(key)
            removed += 1
        except Exception as exc:  # storage is optional for a demo reset
            print(f"  [reset] could not delete object {key}: {exc}")
    return removed


async def reset_demo_data(db: AsyncSession) -> None:
    """Delete everything this script generated, leaving the schema intact.

    Only demo rows go: tickets carrying DEMO_TAG (and, by cascade, their
    comments, attachments, SLA tracking and escalation events), the AI logs
    this script stamped `seed:`, and the chat sessions belonging to demo
    accounts. Users, roles, categories and SLA policies stay — they are
    configuration, and dropping them would orphan anything you created by hand.

    The AI logs matter most here: real timed-out calls left behind a 107-second
    average latency on the dashboard, and no amount of re-seeding fixes that
    while the old rows remain.
    """
    from sqlalchemy import delete

    from app.models.ai_interaction import ChatMessage, ChatSession

    ticket_ids = (await db.execute(
        select(Ticket.id).where(Ticket.tags.any(DEMO_TAG))
    )).scalars().all()

    # Delete the stored files before the rows that point at them. The rows
    # cascade away with their tickets, but the objects do not — nothing else
    # knows they exist once the row is gone, so every --reset would leave the
    # previous run's attachments in the bucket for good.
    removed_objects = await _delete_demo_objects(db, ticket_ids)

    # Escalation events have no cascade from tickets in every path, so clear
    # them explicitly before the tickets they point at.
    if ticket_ids:
        await db.execute(delete(EscalationEvent).where(EscalationEvent.ticket_id.in_(ticket_ids)))
        await db.execute(delete(TicketComment).where(TicketComment.ticket_id.in_(ticket_ids)))
        await db.execute(delete(SLATracking).where(SLATracking.ticket_id.in_(ticket_ids)))
        await db.execute(delete(AIInteractionLog).where(AIInteractionLog.ticket_id.in_(ticket_ids)))

    # Chat history references tickets too; drop messages before sessions.
    session_ids = (await db.execute(select(ChatSession.id))).scalars().all()
    if session_ids:
        await db.execute(delete(ChatMessage).where(ChatMessage.session_id.in_(session_ids)))
    await db.execute(delete(AIInteractionLog))  # includes the real, slow ones
    await db.execute(delete(ChatSession))

    if ticket_ids:
        await db.execute(delete(Ticket).where(Ticket.id.in_(ticket_ids)))

    await db.commit()
    print(
        f"  [reset] Removed {len(ticket_ids)} demo tickets, their comments, "
        f"SLA rows and escalation events, plus all AI history"
    )
    print(f"  [reset] Removed {removed_objects} stored attachment file(s)")


async def main() -> None:
    parser = argparse.ArgumentParser(description="Seed development data.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing demo data first, then re-create it fresh.",
    )
    args = parser.parse_args()

    print("[seed] Starting dev seed…")
    engine = create_async_engine(settings.DATABASE_URL, echo=False)
    session_factory = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)
    async with session_factory() as db:
        if args.reset:
            print("[seed] --reset: clearing existing demo data")
            await reset_demo_data(db)
        await seed(db)
    await engine.dispose()
    print("[seed] Done.")


if __name__ == "__main__":
    asyncio.run(main())
    sys.exit(0)
