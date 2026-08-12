# Technical Architecture

**Status: as-built at `c554e3c`.** Supersedes the aspirational parts of
`architecture.md`, which named modules that do not exist (`core/rbac` as the
enforcement point, `services/sla_engine`, a `notifications` table, an SSE
notification fan-out, a 60-second scheduler). Where this document and that one
disagree, this one was checked against the code.

---

## 1. Shape

```
Browser ──► nginx ──┬──► /            static SPA bundle
                    └──► /api/…       proxy to FastAPI
                                          │
                        ┌─────────────────┴──────────────────┐
                        ▼                                    ▼
                   PostgreSQL 16                        MinIO / S3
                   (system of record)                   (attachment bytes)

                   Ollama (local LLM, OpenAI-compatible /v1)
```

**Redis is provisioned but unused.** It is in `docker-compose`, in
`pyproject.toml` and in `config.py`, and **no application code imports it** —
there is no cache, no rate-limit bucket and no scheduler lock behind it today.
It is drawn out of the diagram deliberately: showing it implies a dependency
that does not exist. Either use it (OPS-2 and SEC-3 both want it) or drop it.

**The nginx proxy is load-bearing.** The client falls back to a same-origin
`/api/v1` base when `VITE_API_BASE_URL` is unset, which avoids CORS and keeps
cookies first-party — but it means nginx must forward `/api` itself. Serving
static files alone gives a site that loads and then 404s every request it
makes.

## 2. Backend layering

```
HTTP → middleware → route → service → repository → model → DB
```

| Layer | Holds | Does not hold |
|---|---|---|
| Middleware | request id, client IP, user agent, error envelope | business rules |
| Routes | parsing, authorisation guards, response shaping | transactions |
| Services | business rules, orchestration | HTTP concepts |
| Repositories | SQLAlchemy queries | rules |
| Models | ORM mapping, shared enums and thresholds | queries |

**Deviation worth knowing:** several routes in `tickets.py` talk to the ORM
directly rather than going through a repository. This is why the ticket state
machine was originally unenforced — `VALID_TRANSITIONS` lived in
`TicketService`, and the HTTP path did not call it. The route now imports and
applies it, but the layering is not uniform.

### Modules

- `api/v1/routes/` — 90 endpoints across 12 modules; `tickets` is the largest
  at 22.
- `services/` — 14 services. `ticket`, `sla`, `escalation`, `routing`,
  `email`, `storage`, `report`, `notification`, `audit`, `org`, `chat_context`,
  `ai`, `ticket_seq`.
- `core/` — `config`, `security`, `authz`, `logging`, `exceptions`.
- `workers/` — two APScheduler jobs (§6).

## 3. Data

26 tables. The ones that carry the domain:

| Table | Note |
|---|---|
| `tickets` | 9 statuses, 4 priorities, 5 sources |
| `ticket_comments` | `is_internal` decides customer visibility |
| `attachments` | `ticket_id` always set; `comment_id` set when sent with a reply |
| `sla_policies`, `sla_tracking` | policy is the rule, tracking is the instance |
| `escalation_rules`, `escalation_events` | rule matched, and what it did |
| `audit_logs` | append-only by convention (see §8) |
| `inbound_emails` | raw intake, deduplicated by `Message-ID` |
| `ai_interaction_logs` | every model call, for cost and latency |
| `org_units`, `hierarchy_levels`, `org_roles` | the visibility tree |

### Two decisions that keep biting if forgotten

**One definition of "open".** `OPEN_STATUSES` in `app/models/ticket.py` is the
single source. There were once six copies that disagreed on `on_hold`, which
showed up as a dashboard card reading 15 opening a list of 17. Risk-band
thresholds (`AI_RISK_HIGH_THRESHOLD`) live in the same place for the same
reason.

**Attachments are half in Postgres and half in object storage.** The row holds
filename, size and checksum; the bucket holds the bytes. Any operation touching
one must consider the other — which is why backup and restore treat them as a
single unit and refuse half a set.

### Migrations

Seven, `0001`–`0007`, and the chain round-trips (7 up, 7 down to base, 7 back
up). `0006` is destructive.

`alembic/env.py` **must** import `app.models`. Without it `Base.metadata` is
empty, autogenerate proposes dropping the whole schema, and `alembic check`
reports a clean bill of health regardless — which is how `inbound_emails` came
to be missing eleven columns its model declared. CI now fails on any table or
column drift.

## 4. Frontend

React 18 + TypeScript + Vite, feature-sliced.

```
src/
  pages/          15 route components
  components/     15 shared components
  features/       api clients and types per domain
  lib/            api.ts (axios + refresh), files.ts, cn.ts
  store/          zustand, persisted auth
```

- **Server state** is React Query. **Client state** is zustand. Auth is the
  only persisted store.
- **Code-split by route** via `React.lazy`, with vendor chunks split so charts
  (411 kB) do not load for someone opening a ticket.
- **Single-flight token refresh.** Three concurrent 401s must produce one
  refresh — the second would present a token the first had just revoked, and
  the server treats reuse as theft and kills the chain.

## 5. Streaming

The assistant streams over SSE. Two constraints:

- **axios cannot be used**, because XHR buffers the body. The streaming client
  uses `fetch` with a `ReadableStream`.
- **nginx must not buffer** `/api/`, or the stream is held until completion and
  arrives as one late blob.

The SSE route opens its own `SessionLocal()`: the injected session closes when
the response starts.

## 6. Background work

| Worker | Interval | Does |
|---|---|---|
| SLA | 5 min | Finds breaches, marks them, runs escalation rules, notifies after commit |
| Email | 2 min | Polls IMAP, parses, threads or creates, deduplicates |

Both are APScheduler jobs inside the API process. **This does not survive
horizontal scaling** — two replicas run two schedulers. A leader lock is
required before running more than one backend container.

Notifications are sent **after** the state change commits. An undelivered email
is recoverable; a rolled-back escalation is not.

## 7. AI integration

- Ollama via the OpenAI-compatible `/v1`, so the SDK is standard.
- `chat_context.py` assembles a grounding block — the open ticket with its
  comments and SLA state, the current page, a digest of the user's queue —
  through the same visibility filter as the REST API.
- Every call is logged with tokens and latency.
- **Degrades rather than fails.** With the model unreachable, an inbound email
  still becomes a ticket carrying its raw body.

## 8. Cross-cutting

**Audit.** Every state change inserts a row with actor, role, IP, request id
and before/after values. **Immutability is by convention only** — no trigger,
no permission grant. This is the largest architectural gap.

**Errors.** One envelope, `{success, data, error: {code, message}, request_id}`.
Clients must read `error.message`; two pages once read FastAPI's `detail`
instead and silently showed generic text for every failure.

**Rate limiting.** Present on the AI routes. There is no general middleware and
no Redis-backed limiter, despite the older document saying otherwise.

## 9. Deployment

Two images, both multi-stage:

- **Backend** — wheels compiled in a discarded builder; the runtime carries the
  venv, `libpq5`, `postgresql-client` (for backup/restore) and `curl` (its own
  healthcheck). Runs as `appuser`.
- **Frontend** — Vite build, then nginx serving static files and proxying
  `/api`.

Both `pip install` steps must copy `app/` **before** installing, because
`pyproject.toml` names it under `[tool.setuptools] packages`.

CI builds and smoke-tests both on every change. CD publishes to GHCR from
`main` and `v*` tags, re-running CI rather than trusting an earlier green run.

## 10. Known architectural debt

1. **Audit immutability** is convention, not enforcement.
2. **Two role definitions** — `core/rbac.py` seeds permission tables that
   nothing reads; `core/authz.py` does the enforcing.
3. **Schedulers in the API process** block horizontal scaling.
4. **Repository layer is bypassed** in parts of `tickets.py`.
5. **No TLS anywhere** in the stack.
6. **Redis is provisioned and unused** — a running dependency nothing needs.
