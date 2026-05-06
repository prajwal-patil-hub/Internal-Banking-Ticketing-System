# Delivery roadmap

| Phase | Scope | Status |
|---|---|---|
| **P0** | Repo layout, docker-compose (postgres+redis+minio), backend skeleton (FastAPI app factory, config, logging, exceptions, db session, /healthz, /readyz), frontend skeleton (Vite+React+TS+Tailwind, layout shell, login shell, dashboard placeholder), CI lint+build workflow, env templates, gitignore/editorconfig, top-level docs | ✅ Done |
| **P1** | users / roles / permissions tables and seeds; password hashing (Argon2); JWT access + refresh issuance / rotation / revocation; login, refresh, logout endpoints; auth dependency + RBAC matrix; login UI wired to backend; protected routes | ✅ Done |
| **P2** | branches, categories, teams CRUD; ticket model + ticket-number generator; ticket create/read/list with filters and pagination | ✅ Done |
| **P3** | Ticket status transitions, assignment, comments (internal flag), attachments to MinIO | ✅ Done |
| **P4** | sla_policies, sla_tracking, APScheduler job, breach detection, on_hold pause | ✅ Done |
| **P5** | Escalations table, notification service + email/sms/in-app adapters (SSE deferred) | ✅ Done |
| **P6** | Audit middleware, immutable trigger, auditor read-only UI | ✅ Done |
| **P7** | Dashboard KPIs, role-specific views, dark-mode polish, responsive layouts | ✅ Done |
| **P8** | Rate limit, MFA enforcement, login-attempt tracking, security headers, structured logs, Prometheus metrics | ✅ Done |
| **P9** | Docker prod images, prod compose + nginx, CI image build, Makefile, runbook | ✅ Done |
