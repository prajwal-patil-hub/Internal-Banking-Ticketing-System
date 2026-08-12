# Product Requirements — SUCCESS Bank Internal Ticketing

**Status: as-built.** This describes the system that exists at `c554e3c`, not a
plan. Where something is specified but not implemented it says so, because a
requirements document that quietly describes intentions as facts is worse than
no document.

---

## 1. Problem

A bank's branches generate operational problems all day — a blocked card, a
duplicated debit, a failed KYC upload, a teller who cannot reach a system.
Without a shared record these arrive by phone and email, land in whoever's
inbox, and there is no answer to "how long has this been open?", "who owns
it?", or, months later during an audit, "who changed what and when?".

## 2. Who uses it

Five roles, one per user account. This is the whole permission model — there is
no per-user override.

| Role | Population | What they come here to do |
|---|---|---|
| `branch_user` | Branch staff | Raise a problem, attach evidence, answer follow-up questions, see only their own tickets |
| `agent` | Central operations | Work any ticket in their org scope: take it, progress it, resolve it |
| `supervisor` | Ops team leads | Agent powers, plus the escalation queue and SLA monitor |
| `admin` | Platform owners | All of the above, plus users, org units, categories, branches |
| `auditor` | Risk / compliance | Read everything. Write nothing, anywhere |

`is_super_admin` is a second tier on top of `admin`, not a sixth role. It
governs who may create or modify another super admin.

## 3. What the product must do

### 3.1 Raising a ticket

- A branch user describes a problem and submits it. **Implemented.**
- Evidence — screenshots, statements, spreadsheets — travels with the report
  rather than being added afterwards. **Implemented.** Up to 15 MB per file;
  images, PDF, text, CSV and Office documents only.
- The ticket is given a number, stamped with SLA deadlines from the matching
  policy, and assigned automatically. **Implemented.**
- Tickets also arrive by email. A reply to an existing thread becomes a comment
  on that ticket rather than a new one. **Implemented**, but requires a real
  IMAP mailbox and is off by default (`IMAP_ENABLED=false`).

**Auto-assignment picks an agent, not whoever is idlest.** Ranking purely on
open-ticket count sends everything to supervisors, who carry no queue and are
therefore always the least loaded. Auditors and branch users are never
candidates — they cannot be assigned work.

### 3.2 Working a ticket

- The lifecycle is a state machine, enforced by the API rather than documented
  and hoped for. **Implemented.**

```
new ──► acknowledged ──► assigned ──► in_progress ──► resolved ──► closed
                                          │  ▲            │
                                    on_hold  │            └──► reopened ──► (assigned)
                                          │  │
                                          └──► escalated ──► in_progress | resolved
```

`closed` is reachable from any open state: closing early is a withdrawal.
`resolved` is not — it requires the ticket to have been worked, so "resolved"
means something.

- Agents and the person who raised it can both comment. A reply can carry
  files, so a fix arrives attached to the answer that explains it.
  **Implemented.**
- Internal notes are invisible to the person who raised the ticket, **and so
  are their attachments.**

### 3.3 Not missing things

- Every ticket gets response and resolution deadlines from an SLA policy.
- A background worker checks for breaches every 5 minutes, marks them, and
  runs the escalation rules.
- Escalation reassigns to the least-loaded holder of the target role, records
  an event, and notifies. It will not fire twice for the same trigger.
- Anyone with agent rights can escalate by hand; it runs the same engine, so
  manual and automatic escalations leave identical evidence.

**Implemented, all of it.**

### 3.4 Seeing the state of things

A dashboard of nine KPI tiles — open, SLA-breached, resolved today, critical,
AI-sorted, arrived by email, escalated, average resolution, and the AI panel.

**Every tile opens the exact set of tickets it counts.** This is a requirement,
not a nicety: a card reading "17 breached" that opens an unfiltered list reads
as a broken filter, and it is asserted in the test suite.

Reports export to CSV, PDF and Excel. **Implemented.**

### 3.5 Proving what happened

Every state change writes an `audit_logs` row with actor, role, IP, request id,
and before/after values. Auditors can read the whole trail.

**Gap:** immutability is by convention. The application only ever inserts, but
there is no database trigger or permission grant preventing an UPDATE or
DELETE by anything holding the connection string. For a system whose value is
its audit trail, that is the most significant outstanding item.

### 3.6 The assistant

A local model (Ollama) answers questions about the work in front of the user.

Three properties are requirements, not features, and all three are enforced
server-side:

1. **It cannot see more than the user can.** Context is fetched through the
   same visibility rules as the REST API.
2. **It says when it does not know**, rather than producing generic advice.
3. **It is bounded** — token budgets for reply, context and history, plus a
   per-user rate limit, with spend visible at `/ai/usage`.

Nothing it does is trusted with a write. It cannot change a ticket.

### 3.7 Signing in

- Argon2id password hashing with a pepper.
- Lockout after 5 consecutive failures for 15 minutes.
- Optional TOTP MFA for **any** user, with ten single-use recovery codes.
- Access tokens 15 minutes, refresh tokens rotated on use; reusing a revoked
  refresh token revokes the whole chain as a theft signal.

## 4. What it deliberately does not do

- **No customer-facing portal.** Branch staff raise tickets on customers'
  behalf. Every account is an employee account.
- **No per-user permissions.** One role per user. Anything finer belongs to
  the org hierarchy.
- **No malware scanning**, therefore no executables or archives accepted.
- **No unattended AI actions.** The assistant advises; people act.
- **No TLS.** Nothing in the stack terminates it — a proxy must sit in front.

## 5. How we know it works

| | |
|---|---|
| Backend tests | 326, against real PostgreSQL |
| Frontend tests | 42 |
| Schema drift | zero, enforced in CI |
| Images | built and smoke-tested on every change |
| Restore | drilled — schema dropped, bucket emptied, restored with matching checksums |

**Not yet verified against production infrastructure:** real MinIO, a real IMAP
mailbox, and CD, whose first run will be its first test.

## 6. Open items, in the order they matter

1. **Audit immutability** at the database level (§3.5).
2. **The permission tables are decorative.** `permissions` and
   `role_permissions` are seeded from `core/rbac.py` but never read; enforcement
   is `core/authz.py` and `require_roles`. Two sources of truth, one of which
   does nothing. See the Security & Access document.
3. **Mypy is advisory** — ~278 errors under `strict`.
4. **No per-branch data retention or archival policy.**
