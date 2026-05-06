# Architecture

## Layers (backend)

```
HTTP -> Middleware -> Controller -> Service -> Repository -> Model -> DB
```

- **Middleware** — request-id, audit context, rate limit, error handler
- **Controllers / routers** — request parsing, response shaping, HTTP only
- **Services** — business rules, orchestration, transactions
- **Repositories** — DB access (SQLAlchemy 2.x async). No business rules.
- **Models** — SQLAlchemy ORM
- **Schemas** — Pydantic DTOs at the API boundary

Cross-cutting modules: `core/config`, `core/security`, `core/logging`,
`core/exceptions`, `core/rbac`, `services/audit_service`,
`services/notification_service`, `services/sla_engine`.

## Frontend

Feature-sliced under `src/features/<feature>/{components,hooks,api,types}` plus
shared `src/components`, `src/lib`, `src/store`. Data is fetched via React
Query against the typed API client in `src/lib/api.ts`.

## Cross-cutting

- **Audit** — every state change persists an immutable `audit_logs` row
  (DB-level trigger + role grant restrict UPDATE/DELETE).
- **SLA** — APScheduler job ticks every 60s, marks breaches, raises escalations.
- **Notifications** — `NotificationService` persists `notifications` rows then
  fans out to channel adapters (email, sms, in-app SSE).

## Security

JWT (access 15m + refresh 7d, rotation, revocation list), Argon2id hashing,
TOTP MFA for admin/supervisor/auditor, login-attempt tracking, account
lockout, Redis-backed rate limit, strict CORS, security headers, output
encoding via React, attachments outside webroot.
