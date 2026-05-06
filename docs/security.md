# Security posture (P8)

## Authentication
- Argon2id password hashing (argon2-cffi defaults: t=3, m=64MB, p=4) with
  optional pepper from env.
- JWT access tokens (15m default) + opaque refresh tokens (7d, hashed in
  DB). Refresh tokens are rotated on every use; presenting a revoked
  refresh token revokes the entire chain for that user (theft signal).
- Login attempts (success/failure) are recorded with IP + UA. After 5
  consecutive failures the account locks for 15 minutes.
- Successful logins emit an `auth.login` audit row.

## MFA (TOTP)
- Per-user enrolment via `/api/v1/mfa/enroll` (returns base32 secret +
  otpauth URI for any authenticator app).
- `POST /mfa/verify` flips `mfa_enabled = true` after first valid code.
- Enforcement of MFA at login for privileged roles
  (admin / supervisor / auditor) is wired through the `mfa_enabled`
  flag — UI + login flow upgrade lands in v2.

## Authorization
- Role + permission codes seeded by `core/rbac.py`; the DB is the
  source of truth at runtime.
- `require_roles(...)` and `require_permissions(...)` dependencies guard
  every privileged route. Frontend guards mirror them but are NOT
  authoritative.
- Branch-user reads are scoped at the repository layer (their
  `branch_id` filters every list/get).

## Rate limiting
- Redis fixed-window counter (1 minute):
  - **10 / IP** for `POST /auth/login`
  - **120 / actor** (or IP if anon) for any non-GET method.
- Health, readiness, OpenAPI, and `/metrics` are exempt.

## HTTP hardening
- `SecurityHeadersMiddleware` sets:
  X-Content-Type-Options, X-Frame-Options, Referrer-Policy,
  Permissions-Policy, CSP (script-src 'self'), COOP, CORP. HSTS in
  production only.
- CORS allowlist via `CORS_ORIGINS`.
- Standard response envelope; raw stack traces never leak.
- Pydantic v2 strict validation at boundaries; SQLAlchemy parameterized
  queries throughout.
- Attachments: content-type allowlist, 10 MB cap, served from S3-compat
  storage outside the webroot. Storage key is randomised + ticket-scoped.

## CSRF
- The frontend talks to the API as an SPA with a Bearer header (not a
  cookie session). Browsers will not auto-attach the Authorization
  header on cross-site requests, so CSRF is not a relevant attack class
  for this deployment. If we ever switch to cookie sessions, we will
  add SameSite=strict + a double-submit token.

## Audit
- `audit_logs` is append-only at the DB level (BEFORE UPDATE/DELETE
  trigger raises). The DB role used in production is granted only
  `INSERT, SELECT` on this table.
- Every state mutation (login, ticket lifecycle, comments) writes an
  audit row through one chokepoint (`AuditService.log`).

## Observability
- Structured JSON logs (`structlog`) carry `request_id`, `client_ip`,
  method, path, level, and any kwargs.
- Prometheus metrics on `/metrics`:
  - `http_requests_total{method,path,status}`
  - `http_request_duration_seconds_bucket{method,path}`
  - `app_info{env,name}`
- Health: `/api/v1/healthz` (process), `/api/v1/readyz` (DB reachable).

## Secrets & deploy
- All secrets via env vars (`backend/.env.example` is the template).
- HSTS enabled only when `APP_ENV=production`.
- Long-running background work (SLA scheduler) protected by a Redis
  `SET NX` lock so horizontal scaling stays safe.
