# Delivery roadmap

| Phase | Scope | Status |
|---|---|---|
| **P0** | Repo layout, docker-compose (postgres+redis+minio), backend skeleton (FastAPI app factory, config, logging, exceptions, db session, /healthz, /readyz), frontend skeleton (Vite+React+TS+Tailwind, layout shell, login shell, dashboard placeholder), CI lint+build workflow, env templates, gitignore/editorconfig, top-level docs | ✅ Done |
| **P1** | users / roles / permissions tables and seeds; password hashing (Argon2); JWT access + refresh issuance / rotation / revocation; login, refresh, logout endpoints; auth dependency + RBAC matrix; login UI wired to backend; protected routes | ⏳ Next |
| **P2** | branches, categories, teams CRUD; ticket model + ticket-number generator; ticket create/read/list with filters and pagination | |
| **P3** | Ticket status transitions, assignment, comments (internal flag), attachments to MinIO | |
| **P4** | sla_policies, sla_tracking, APScheduler job, breach detection, on_hold pause | |
| **P5** | Escalations table, notification service + email/sms/in-app adapters, in-app SSE | |
| **P6** | Audit middleware, immutable trigger, auditor read-only UI | |
| **P7** | Dashboard KPIs, role-specific views, dark-mode polish, responsive layouts | |
| **P8** | Rate limit, MFA enforcement, login-attempt tracking, security headers, structured logs, Prometheus metrics | |
| **P9** | Docker prod images, GitHub Actions CD, runbook, demo seed | |
