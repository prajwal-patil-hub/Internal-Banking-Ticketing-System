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
| `priya.sharma@successbank.local` | `Passw0rd@123` | supervisor |
| `meera.nair@successbank.local` | `Passw0rd@123` | supervisor |
| `rahul.verma@successbank.local` | `Passw0rd@123` | agent |
| `aisha.khan@successbank.local` | `Passw0rd@123` | agent |
| `vikram.rao@successbank.local` | `Passw0rd@123` | agent |
| `deepak.iyer@successbank.local` | `Passw0rd@123` | auditor |
| `sunita.desai@successbank.local` | `Passw0rd@123` | branch_user |
| `arjun.mehta@successbank.local` | `Passw0rd@123` | branch_user |

The seed also loads 21 demo tickets spanning every status, priority, and SLA
state (breached / at-risk / on-time), plus comments and escalation events — so
Tickets, SLA Monitor, and Escalations all have real data to show. Re-running
the seed is safe; it detects the demo set and skips it.

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
