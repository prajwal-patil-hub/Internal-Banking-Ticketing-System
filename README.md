# SUCCESS Bank — Internal Ticketing & CRM

Production-style internal ticketing platform for a bank. Branches raise issues,
admin triages, agents resolve, supervisors monitor SLAs, auditors review
immutable logs.

> Status: **P0–P8 delivered.** Auth and RBAC, the ticket lifecycle, SLA engine,
> escalations, audit trail, attachments, email intake, MFA with recovery codes,
> and a grounded local-model assistant are all wired end to end. See
> `docs/architecture.md` for the design and `docs/roadmap.md` for the phases.

## Stack

| Layer       | Tech |
|-------------|------|
| Frontend    | React 18 + TypeScript + Vite + TailwindCSS + React Query + React Router + Zustand |
| Backend     | FastAPI (Python 3.12) + SQLAlchemy 2 (async) + Alembic + Pydantic v2 |
| Auth        | JWT (access + refresh) + Argon2id + TOTP MFA |
| DB          | PostgreSQL 15 (Supabase compatible) |
| Cache/Queue | Redis 7 |
| Storage     | S3-compatible (MinIO local) |
| Scheduler   | APScheduler |
| Observability | structlog (JSON) + Prometheus metrics |
| Container   | Docker + docker-compose |

## Quick start (local)

```bash
# 1. Configure
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

# 2. Bring up the stack
docker compose -f infra/docker-compose.yml up -d

# 3. Apps
#    Frontend  : http://localhost:5173
#    Backend   : http://localhost:8000/api/docs
#    MinIO UI  : http://localhost:9001
```

The stack seeds itself on first boot. Sign in with any of these:

| Email | Password | Role |
|---|---|---|
| `admin@successbank.local` | `Admin@123456` | admin |
| `super.admin@successbank.local` | `Passw0rd@123` | admin + **super admin** |
| `priya.sharma@successbank.local` | `Passw0rd@123` | supervisor |
| `meera.nair@successbank.local` | `Passw0rd@123` | supervisor |
| `rahul.verma@successbank.local` | `Passw0rd@123` | agent |
| `aisha.khan@successbank.local` | `Passw0rd@123` | agent |
| `vikram.rao@successbank.local` | `Passw0rd@123` | agent |
| `deepak.iyer@successbank.local` | `Passw0rd@123` | auditor |
| `sunita.desai@successbank.local` | `Passw0rd@123` | branch_user |
| `arjun.mehta@successbank.local` | `Passw0rd@123` | branch_user |

The seed loads ~56 tickets spread over six weeks — every status and priority,
a believable mix of breached / at-risk / on-time, comments, escalation events,
and AI interaction history so the dashboard's AI panel reports real numbers.

Re-running the seed is safe; it detects the demo set and skips it. To throw the
data away and generate it afresh:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python scripts/seed_dev.py --reset
```

`--reset` removes the demo tickets and **all** AI interaction history, then
rebuilds. Users, roles, categories and SLA policies are configuration and are
left alone. Clearing the AI history matters: real timed-out calls otherwise
leave a 107-second average latency on the dashboard that no amount of
re-seeding will shift.

## Ticket intake

A ticket raised through the API gets its SLA deadlines stamped and is
auto-assigned to the agent with the lightest open queue. Agents are preferred
over supervisors — ranking on workload alone sends everything to whoever is
idlest, which is reliably a supervisor, and frontline work would skip the
agents entirely. Auditors and branch users are never candidates.

Pass `auto_assign: false` when creating a ticket to leave it unassigned for
manual triage.

### By email

With `IMAP_ENABLED=true` the mail worker polls the support mailbox every two
minutes. A new message becomes a ticket; a reply is threaded onto the ticket it
belongs to as a public comment, matched on `In-Reply-To`, `References` or an
`X-Ticket-ID` header rather than on the subject line alone. Messages are
de-duplicated by `Message-ID`, so a mailbox re-scan cannot create the same
ticket twice, and obvious spam is scored and parked instead of raised.

The model is asked to extract a title, category and priority from the body. If
it is unreachable the message still becomes a ticket, carrying the subject and
the raw body — a triage backlog is recoverable, a silently dropped customer
email is not.

`infra/docker-compose.yml` includes Mailpit, which catches everything the system
**sends** — SLA breach warnings, escalation notices — at <http://localhost:8025>,
so those stop failing silently in development.

Mailpit speaks SMTP, not IMAP, so it cannot feed the intake poller. Point
`IMAP_HOST`/`IMAP_USER`/`IMAP_PASSWORD` at a real mailbox to exercise inbound
mail, or drive `EmailService.process_inbound_email()` directly with a parsed
message to test the parse → ticket path without a server.

### Attachments

Images, PDFs, text, CSV and Office documents, up to 15 MB each, stored in
S3/MinIO under randomised per-ticket keys. Files attach at three points:

- **Raising a ticket.** A screenshot of the error or the statement in question
  usually explains a problem faster than describing it, so the evidence travels
  with the report rather than arriving later from a side panel.
- **Replying.** An agent's fix — a corrected statement, a screenshot of the
  working screen — attaches to the reply that explains it, and the person who
  raised the ticket sees the two together.
- **The ticket itself**, from the Attachments panel, which lists every file on
  the ticket and marks the ones that came in with a reply.

The raiser can answer on their own ticket and attach to it too, which is what
keeps a "can you send a screenshot of the error?" exchange inside the system
instead of pushing it out to email.

Two rules worth knowing:

**A file on an internal note is as invisible as the note.** Filtering the note
while still serving its attachment would leak exactly what the flag exists to
withhold, and the file is usually the sensitive part. Enforced on both the
listing and the download, and the download answers 404 rather than 403 so the
response does not confirm a hidden note exists.

**Files stream through the API**, not via presigned URLs. A presigned URL is a
bearer token in a query string: it outlives the session, survives in browser
history and proxy logs, and grants access to anyone holding it. Every read goes
through the same ticket permission check as the rest of the record. Executables
and archives are refused outright — there is no malware scanner here, and an
unscanned archive is the classic delivery route.

## Branch network

**Branches** in the sidebar shows the physical network: which branches are
serving customers, who manages each, and how much work they are carrying
against their capacity. `/branches` used to redirect to the org hierarchy,
which answers a different question — org units are the reporting tree, branches
are places with staff and a service state.

`status` is deliberately separate from `is_active`: a decommissioned branch is
inactive, a branch with a dead ATM is active but degraded, and one boolean
cannot express both.

Ticket counts and load are computed per request rather than stored on the row.
A denormalised counter would need every ticket transition to remember to adjust
it, and the first missed update leaves a number that is wrong forever with
nothing to reveal it.

## Roles

One role per user, enforced centrally in `backend/app/core/authz.py`:

| Role | Can do |
|---|---|
| `branch_user` | Raise tickets, see only their own, comment, close/reopen them |
| `agent` | Work any ticket: assign, progress, resolve, pause SLA, AI helpers |
| `supervisor` | Agent powers plus the escalation queue, SLA monitor, user directory |
| `admin` | All of the above plus user, org and category administration |
| `auditor` | **Read only** — tickets, audit log, dashboards, reports. No writes at all |

`is_super_admin` is a second tier on top of `admin`: only a super admin can grant
the super-admin flag or modify another super admin's account. Without that,
any admin could reset the super admin's password and take the account over.

The ticket lifecycle is enforced on the API, not just documented — illegal jumps
(`new → resolved`, `closed → new`) are rejected with the list of moves that are
actually available from the current state.

## Two-factor authentication

Any user can enrol from **Security** in the sidebar: scan the QR code with an
authenticator app, confirm one code, and MFA is on. After that, signing in asks
for a code before issuing any token.

Turning MFA off requires the account password, not just a live session — a
stolen access token must not be enough to strip the second factor.

Enrolment issues **ten single-use recovery codes**, shown once and never again:
only their SHA-256 hashes are stored, which is what makes them safe to keep at
all. Any one of them can be typed in place of a code at sign-in, so a lost
phone is not a lost account. Spending a code marks it used rather than deleting
it, so "a recovery code was used at 09:14" stays answerable after an incident,
and replaying one fails. Regenerating the set requires the account password,
since it invalidates whatever the real owner is holding.

If every code is also gone, an admin can still clear the enrolment
(`POST /api/v1/users/{id}/mfa/reset`).

## Escalation

When the SLA worker finds a breach it now evaluates the escalation rules rather
than only marking the ticket red. The matching rule — most specific first, with
`priority_threshold` read as a minimum so a "high" rule also covers critical —
decides who the ticket goes to; the ticket moves to `escalated`, is reassigned
to the least-loaded holder of the target role, an `escalation_events` row is
written, and the target plus the manager list are emailed.

Anyone with agent rights can also escalate by hand from the ticket page, which
runs the same engine so manual and automatic escalations leave identical
evidence.

Two guarantees worth knowing:

- **It will not escalate the same ticket twice.** The worker revisits every
  overdue ticket each run, so an unresolved event for the same trigger
  suppresses another. Without that the event log would gain a row per ticket
  per run and the target would be emailed every five minutes.
- **A failed email does not lose the escalation.** Notifications are sent after
  the state change is committed, and a delivery failure is logged rather than
  raised.

`GET /api/v1/tickets/{id}/timeline` returns the ticket's whole history —
creation, comments, status changes from the audit log, and escalations — merged
into one chronological feed, which is what the ticket page's timeline renders.

## How the AI assistant works

The assistant is **grounded**: before each reply the server assembles a CONTEXT
block from the database — the ticket you have open with its comments and SLA
state, the screen you are on, and a digest of your own queue — and gives that to
the model. So it can answer "what is this ticket about?" or "what should I pick
up first?" from the actual record rather than from memory.

Three properties matter in production, and all three are enforced server-side:

- **It cannot see more than you can.** Context is fetched through the same
  visibility rules as the REST API. Point it at a ticket your role cannot read
  and it is told the ticket is unavailable — no title, no number, nothing.
- **It says when it does not know.** The prompt requires a one-sentence "I
  can't see that" instead of generic advice. An assistant that invents ticket
  facts in a bank is worse than one that declines.
- **It is bounded.** Replies, context and replayed history each have a budget
  (`AI_CHAT_MAX_TOKENS`, `AI_CONTEXT_CHAR_BUDGET`, `AI_HISTORY_CHAR_BUDGET`),
  and each user has a per-minute call limit. `GET /api/v1/ai/usage` reports
  token spend and latency by interaction type so the cost is visible.

## Local AI (Ollama)

The AI assistant runs against a local model, so nothing leaves your machine and
there is no API key. Install [Ollama](https://ollama.com), then:

```bash
ollama pull glm4          # or set LLM_MODEL to any model you have
```

**macOS: Ollama binds to `127.0.0.1` by default, which the Docker VM cannot
reach.** Without this step the assistant will report that it cannot connect:

```bash
launchctl setenv OLLAMA_HOST 0.0.0.0   # then restart Ollama
```

To check the wiring, call `GET /api/v1/ai/health` (or just send a chat message —
failures come back as a plain-English explanation rather than a generic error).
It reports whether Ollama is reachable, which models it has, and what to fix.

Note that the first reply after an idle period is slow — the model has to load
before it emits a token, which on an M2 Mac can take under a minute. Timeouts on
both sides are sized for that (`AI_TIMEOUT_SECONDS`, default 180s).

## Walking the system

A pass that touches every subsystem, in an order where each step sets up the
next. Roughly fifteen minutes.

**1. Bring it up and sign in as an agent.**

```bash
docker compose -f infra/docker-compose.yml up -d
```

Open <http://localhost:5173> as `aisha.khan@successbank.local` / `Passw0rd@123`.

**2. Check the dashboard adds up.** Click any KPI card — *Open*, *SLA
Breached*, *Critical*, *AI Sorted*, *Escalated*, and the three live tiles in the
AI panel. Each opens a ticket list filtered to exactly the number on the card.
That equality is the point: a card that opens a list with a different total
reads as a broken filter, so it is verified on every build.

**3. Raise a ticket and watch it route itself.** *New Ticket* → save. It comes
back already `assigned`, with an owner and both SLA deadlines stamped. The
assignee is the agent with the lightest open queue, never a supervisor or an
auditor.

**4. Attach files, both ways.** Raise a second ticket as
`sunita.desai@successbank.local` (a branch user) and drag a screenshot and a PDF
onto the form *before* submitting — they upload with the ticket. Try an `.exe`
or a `.zip` too: refused by type, before a byte is stored.

Then pick that ticket up as an agent, reply with a file attached, and switch
back to Sunita: the file appears under the agent's reply, not in a separate
pile. Now post an **internal note** with a file attached as the agent — Sunita
can neither see it nor download it, even with the attachment id.

**5. Try an illegal move.** Push the ticket straight from `assigned` to
`resolved`. It is rejected, and the error names the moves that *are* available.
`resolved` requires the ticket to have been worked; `closed` is reachable from
anywhere, because closing early is a withdrawal rather than a resolution.

**6. Escalate it.** Use *Escalate* on the ticket page. The ticket moves to
`escalated`, is reassigned to the least-loaded holder of the target role, and
gains an entry in the timeline. Escalating again does nothing — the same
trigger will not fire twice.

**7. Confirm the auditor really is read-only.** Sign in as
`deepak.iyer@successbank.local`. Every dashboard, report and audit log opens;
every write — comment, status change, upload — is refused. This is enforced in
`backend/app/core/authz.py`, not in the UI, so hitting the API directly gets the
same answer.

**8. Enrol a second factor.** As `super.admin@successbank.local`, open
**Security** → scan the QR → confirm one code. Save the ten recovery codes it
shows you. Sign out, sign back in — it now asks for a code. Use a **recovery
code** instead of the app. It works once; try the same one again and it is
rejected.

**9. Export something.** On **Reports** or the dashboard, export as PNG, PDF and
Excel. The PDF carries each chart's image above the numbers behind it; the
workbook has a summary sheet plus one sheet per chart.

**10. Ask the assistant.** Open a ticket and ask *"what is this about?"*, then
*"what should I pick up first?"*. It answers from the record, streaming as it
goes. Then point it at a ticket your role cannot see — it declines rather than
inventing one. If it cannot reach the model, `GET /api/v1/ai/health` says why in
plain English.

**11. Check the outbound mail.** Open Mailpit at <http://localhost:8025> — the
escalation you raised in step 6 is sitting there. Inbound intake needs a real
IMAP mailbox (see *Ticket intake → By email*); to exercise the parse → ticket
path without one:

```bash
docker compose -f infra/docker-compose.yml exec backend python -c "
import asyncio
from app.db.session import SessionLocal
from app.services.email_service import EmailService, _parse_raw_email

RAW = b'''From: Priya Customer <priya@example.com>
To: support@successbank.local
Subject: Card blocked after travel
Message-ID: <demo-1@example.com>

My debit card was blocked while travelling. Please unblock it.
'''

async def main():
    async with SessionLocal() as db:
        rec = await EmailService(db).process_inbound_email(_parse_raw_email(RAW))
        print(rec.status, rec.ticket_id)

asyncio.run(main())
"
```

Run it twice: the second call returns `duplicate` and creates nothing.

## Operations

[`docs/runbook.md`](docs/runbook.md) covers deploying, rolling back, health
checks, credential rotation, and the failure modes that actually occur here —
Ollama unreachable, storage down, escalations not firing.

Backups are the part worth reading before you need them:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python scripts/backup.py --out /backups --keep 14
```

A ticket's attachments live in two stores — the row in Postgres, the bytes in
S3 — so a database-only backup restores to a system where every attachment
lists correctly and fails on download. `backup.py` captures both and deletes
the set rather than write half of one; `restore.py` refuses a half set and
verifies row counts and object presence before reporting success.

The drill in the runbook has been run against a seeded database: after dropping
the schema and emptying the bucket, restore brought back 56 tickets and 15
attachments, each downloading with a checksum identical to before the backup.

### Running the checks yourself

```bash
# Backend suite
docker compose -f infra/docker-compose.yml exec backend python -m pytest -q

# Frontend typecheck and production build
cd frontend && npx tsc --noEmit && npm run build

# Confirm the models and the database still agree
docker compose -f infra/docker-compose.yml exec backend alembic check
```

`alembic check` is worth running after any model change. It was reporting a
clean bill of health while `inbound_emails` was missing eleven columns, because
`alembic/env.py` never imported the models and its metadata was empty. With the
import restored the check is real, and email intake works.

## Repository layout

```
backend/    FastAPI service (clean architecture: api → services → repositories → models)
  scripts/  seed_dev.py, backup.py, restore.py
frontend/   React SPA (feature-sliced)
infra/      docker-compose
docs/       architecture, roadmap, runbook
.github/    CI workflow
```

## Roadmap (high level)

- **P0** Bootstrap *(✓)*
- **P1** Auth & RBAC *(✓)*
- **P2** Core domain (branches, categories, teams, tickets) *(✓)*
- **P3** Ticket workflow (assignment, comments, attachments) *(✓)*
- **P4** SLA engine *(✓)*
- **P5** Escalations & notifications *(✓)*
- **P6** Audit trail *(✓)*
- **P7** UI polish *(✓)*
- **P8** Hardening (rate limit, MFA, metrics) *(✓)*
- **P9** DevOps finalisation — CI gates, deployment, backup/restore drill

## License

Internal — all rights reserved.
