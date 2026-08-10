# SUCCESS Bank — Internal Ticketing & CRM

Production-style internal ticketing platform for a bank. Branches raise issues,
admin triages, agents resolve, supervisors monitor SLAs, auditors review
immutable logs.

> Status: **Phase P0 — Bootstrap complete.** See `docs/architecture.md` for the
> full plan and `docs/roadmap.md` for phase-by-phase delivery.

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

There are no printed backup codes yet, so a lost device is recovered by an
admin clearing the enrolment (`POST /api/v1/users/{id}/mfa/reset`).

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

## Repository layout

```
backend/    FastAPI service (clean architecture: api → services → repositories → models)
frontend/   React SPA (feature-sliced)
infra/      docker-compose, nginx, CI configs
docs/       architecture, API reference, runbook
.github/    CI workflows
```

## Roadmap (high level)

- **P0** Bootstrap *(✓)*
- **P1** Auth & RBAC
- **P2** Core domain (branches, categories, teams, tickets)
- **P3** Ticket workflow (assignment, comments, attachments)
- **P4** SLA engine
- **P5** Escalations & notifications
- **P6** Audit trail
- **P7** UI polish
- **P8** Hardening (rate limit, MFA, metrics)
- **P9** DevOps finalisation

## License

Internal — all rights reserved.
