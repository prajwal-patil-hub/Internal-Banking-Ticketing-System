# Session context — claude/analyze-and-fix-code-e1Dvq

Last updated 2026-05-20. This file exists so a new Claude session can resume
without re-deriving the project state. Keep it short, append rather than
rewrite, and always link to commits where they exist.

---

## Repository

- Project: **Internal Banking Ticketing System** (FastAPI + React + Postgres + Redis + MinIO).
- Working branch: `claude/analyze-and-fix-code-e1Dvq`.
- Parent commit: PR #2 merge on `main` (`7b1ddaa`) — initial AI-native redesign.
- Backend runs Python 3.12 in Docker (compose at `infra/docker-compose.yml`).
- Frontend runs Vite + React 18 + Tailwind. Dev port 5173, backend 8000.

## State summary

Backend:

- Models: User, Role, Permission, Branch, Ticket (+Category, +SubCategory),
  TicketComment, Attachment, SLA (policy + tracking), Escalation (rule + event),
  AuditLog, InboundEmail, AI (ChatSession, ChatMessage, AIInteractionLog).
- Services: ticket_service, sla_service, routing_service, email_service,
  ai_service, audit_service, notification_service, auth_service.
- Workers: APScheduler-driven email poller (off in dev) and SLA breach scanner.
- Routes (all under `/api/v1`): auth, users, roles, branches, escalations,
  tickets, categories, ai, dashboard, audit, health.
- Migrations: `0001_auth_initial`, `0002_tickets_ai_email`. Compose runs
  `alembic upgrade head` before uvicorn (production should run it separately).
- Tests: 38 pytest cases against real Postgres + Redis. See `backend/tests/`.
  Includes a drift-detector that greps every frontend `api.<verb>(...)` call
  and asserts each maps to a backend route with the right method.

Frontend:

- Pages: Login, Dashboard, Tickets, TicketDetail, CreateTicket, Audit,
  Users & Roles, Branches, Escalations, SLA Monitor, Forbidden, Placeholder.
- Components: Button (variants/sizes/loading), Card, StatusBadge,
  PriorityBadge, SLABadge, AIBadge, TicketCard, AIChatWidget (floating).
- Palette: old-money — cream paper base `#FBF8F1`, deep forest brand
  `#1F3A2E`, burnished brass accent `#A88959`, oxblood for danger.
- Build: `npx vite build` is clean.

## Closed issues (by commit, newest first)

| Commit | What |
|---|---|
| _this_ | Replaced 4 placeholder pages (SLA, Escalations, Branches, Users) with real screens, added backend list endpoints for users / roles / branches / escalations, fixed internal-comment visibility on unassigned tickets. |
| 41fd12b | Fixed 9 broken UI buttons (frontend↔backend path/method drift on status / assign / AI summarize / AI suggest / pause SLA / resume SLA / AI chat sessions). Old-money palette swap. Button component polished (variants/sizes/loading/focus-visible). Drift-detector test that catches this whole class. |
| c6128ac | Integration test suite (24 cases). Caught and fixed two bugs: duplicate index on `inbound_emails.thread_id`, rate-limit headers lost on error responses. |
| 4c6e48c | gitignore Redis persistence artifacts (`dump.rdb`). |
| 53f325f | Redis-backed rate limiting on auth/login (10/min/ip), auth/refresh (30/min/ip), POST /tickets (30/min/user), AI endpoints (20/min/user). Fail-open on Redis outage. Standard `Retry-After` + `X-RateLimit-*` headers. |
| f762898 | `scripts/seed_admin.py` for local-dev login. |
| e2a082d | Auto-run alembic in backend compose CMD. |
| f2c3db6 | MinIO healthcheck uses `mc ready local` (image no longer ships curl). |
| 2d8584a | Added `values_callable` to every Enum column. Tickets table inserts/reads now work with the lowercase PG enum types created by migration 0002. Pagination envelope unwrap in frontend (`page_size` → `per_page`, `data` → `{items,total,...}`). |

## Known open work

- Production deployment hardening: pin image tags, externalise secrets, put
  TLS in front, run migrations as a separate Job (not the app CMD), set
  `restart: on-failure:5` to surface migration loops in seconds not hours.
  Sketched in past replies, not yet implemented.
- PII redaction before LLM calls (`ai_service.py` still forwards raw text).
- Prometheus `/metrics` endpoint (deps already include `prometheus-client`).
- Idempotency-keyed email worker + DLQ table.
- GitHub Actions CI (lint + tests + alembic check).
- RAG / vector store / knowledge base for the AI assistant.
- Playwright UI smoke tests against the live container.

## How to continue in a fresh session

```text
1. Read this file: docs/SESSION_CONTEXT.md.
2. git log --oneline -20            # see what landed since last commit listed above
3. backend tests: cd backend && python -m pytest -q
4. frontend build: cd frontend && npx vite build
5. Then pick from "Known open work" or ask the user.
```

## Standing operating rules

- Branch: `claude/analyze-and-fix-code-e1Dvq` for everything on this thread.
- Don't run alembic in production via the app CMD — that's a dev shortcut.
- The Postgres enum types use lowercase values; every SQLAlchemy Enum column
  must keep `values_callable=lambda x: [e.value for e in x]`.
- Frontend axios baseURL strips `/api/v1`, so `api.get('/tickets')` hits
  `/api/v1/tickets`.
- Pagination contract from backend is `{success, data: [items], meta:
  {pagination: {page, size, total, pages}}, error}`. Frontend api modules
  unwrap it via `unwrapPaginated`. Don't change one side without the other.
- Don't commit `backend/dump.rdb` (Redis persistence) or anything from
  `frontend/dist/` (build output). Both are gitignored.
