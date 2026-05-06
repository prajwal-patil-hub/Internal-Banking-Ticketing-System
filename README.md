# SUCCESS Bank — Internal Ticketing & CRM

Production-style internal ticketing platform for a bank. Branches raise
issues, admin triages, agents resolve, supervisors monitor SLAs, auditors
review immutable logs.

> Status: **All nine phases delivered (P0 → P9).**
> See [`docs/architecture.md`](docs/architecture.md) for the architecture,
> [`docs/roadmap.md`](docs/roadmap.md) for the phased delivery,
> [`docs/security.md`](docs/security.md) for the security posture, and
> [`docs/runbook.md`](docs/runbook.md) for the day-2 playbook.

## Stack

| Layer         | Tech |
|---------------|------|
| Frontend      | React 18 + TypeScript + Vite + TailwindCSS + React Query + React Router + Zustand |
| Backend       | FastAPI (Python 3.12) + SQLAlchemy 2 (async) + Alembic + Pydantic v2 |
| Auth          | JWT (access + refresh, rotation) + Argon2id + TOTP MFA |
| DB            | PostgreSQL 15 (Supabase compatible) |
| Cache / queue | Redis 7 (rate limit, scheduler lock) |
| Storage       | S3-compatible (MinIO local; Supabase / S3 in prod) |
| Scheduler     | APScheduler with Redis SET-NX cluster lock |
| Observability | structlog (JSON) + Prometheus `/metrics` |
| Container     | Docker + docker-compose (dev + prod) |

## Quick start (local)

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

make up          # postgres + redis + minio + backend + frontend
make migrate     # apply Alembic migrations
make seed        # roles, permissions, demo branches / categories / tickets / users
```

URLs:
- Frontend     http://localhost:5173
- Backend docs http://localhost:8000/api/docs
- MinIO UI     http://localhost:9001
- Metrics      http://localhost:8000/metrics

Demo passwords are printed on the first `make seed` run.

## Production-style stack

```bash
make prod-build
make prod-up        # nginx :80 -> { /api, /metrics, * }
```

See [`docs/runbook.md`](docs/runbook.md) for migration / scaling /
on-call instructions.

## Repository layout

```
backend/   FastAPI service — clean architecture
           api → services → repositories → models, plus adapters & workers
frontend/  React SPA — feature-sliced
           features/<area>/{api,components,hooks,types}
infra/     docker-compose (dev + prod), nginx, CI configs
docs/      architecture, security posture, runbook, roadmap
.github/   CI / Docker workflow
Makefile   Day-1 commands: up, migrate, seed, test, prod-up, …
```

## What's inside

- **Roles & permissions** — `branch_user`, `agent`, `admin`, `supervisor`,
  `auditor`. Permission matrix in `app/core/rbac.py`; route guards via
  `require_roles(...)` and `require_permissions(...)`.
- **Tickets** — `TKT-YYYY-NNNNNN`, server-side ticket-number sequence,
  branch-scoped reads, full filter & pagination, attachments to S3.
- **Workflow** — state machine validated against `ALLOWED_TRANSITIONS`.
  Transitions emit notifications to the right people and audit rows.
- **SLA engine** — per-priority policy (banking-standard defaults),
  per-ticket tracking with **pause on On Hold**, breach scan every 60 s
  (Redis-locked), idempotent on retry.
- **Escalations** — first-class table, manual + automatic (on breach),
  L1/L2 progression, supervisor in-app + email alerts.
- **Notifications** — adapter-pluggable (in-app + email + SMS stub).
  Live bell in the topbar with unread-count badge.
- **Audit log** — append-only at the **DB level** (BEFORE UPDATE/DELETE
  trigger raises). Every state change goes through one chokepoint.
- **Hardening** — Redis fixed-window rate limit (10/min/IP on login,
  120/min/actor on writes), CSP / HSTS / X-Frame-Options / Permissions-
  Policy, TOTP MFA enrol/verify/disable, Prometheus metrics on `/metrics`,
  account lockout after 5 failed logins, refresh-token rotation +
  theft detection.

## Roadmap

| Phase | Scope | Status |
|---|---|---|
| **P0** | Bootstrap (repo, infra, skeletons, CI) | ✅ |
| **P1** | Auth & RBAC | ✅ |
| **P2** | Core domain (branches, categories, teams, tickets) | ✅ |
| **P3** | Ticket workflow (transitions, comments, attachments) | ✅ |
| **P4** | SLA engine (policies, scheduler, breach detection) | ✅ |
| **P5** | Escalations & notifications | ✅ |
| **P6** | Audit trail (immutable trigger) | ✅ |
| **P7** | UI polish (role-aware dashboard, responsive, toasts) | ✅ |
| **P8** | Hardening (rate limit, MFA, headers, metrics) | ✅ |
| **P9** | DevOps (prod images, prod compose, runbook, CI image build) | ✅ |

## License

Internal — all rights reserved.
