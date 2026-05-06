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
