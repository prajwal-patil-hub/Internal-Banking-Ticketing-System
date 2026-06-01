# Project Rules

Single source of truth for how this codebase is built and maintained.
Everything below was distilled from the existing repo on the branch
`claude/analyze-and-fix-code-e1Dvq`. Anything that contradicts these rules
is a bug to file or fix.

---

## 1. Architecture

- **Backend**: FastAPI (Python 3.12) + async SQLAlchemy + Postgres + Redis + MinIO.
- **Frontend**: React 18 + Vite + Tailwind + TanStack Query + Zustand.
- **Pattern**: Modular monolith. Models → repositories (where they exist) →
  services → API routes. Frontend talks to one axios baseURL = `/api/v1`.
- **Workers**: APScheduler jobs (`workers/`), started in the app lifespan.
  Production-shaped deployments must move scheduled work to a dedicated
  process with a leader lock — never run on N replicas.
- **AI provider**: Pluggable via `AI_PROVIDER` (`groq` default, `anthropic`
  alternative). All LLM calls go through `app/utils/ai_client.call_llm`.

## 2. Folder conventions

```
backend/
  app/
    api/v1/routes/       # FastAPI APIRouter modules (one per resource)
    core/                # config, exceptions, logging, redis, rate_limit, rbac, security
    db/                  # base, session, seed, demo_seed
    middleware/          # ASGI middleware
    models/              # SQLAlchemy ORM (one file per aggregate root)
    repositories/        # Pure data access (no business rules)
    schemas/             # Pydantic request/response schemas
    services/            # Business rules; never import from api.*
    utils/               # Stateless helpers (ai_client, etc.)
    workers/             # APScheduler jobs
  tests/                 # pytest, async, real Postgres + Redis
  alembic/versions/      # Strict linear history, immutable once on main

frontend/
  src/
    app/                 # App.tsx, AppLayout, RequireAuth, routing
    components/          # Presentational widgets only
    features/<area>/api.ts  # Typed axios wrappers; one file per area
    pages/               # Route-level components
    store/               # Zustand stores
    styles/              # globals.css
    lib/                 # axios client, utils
```

## 3. Naming

- **Python**: `snake_case` for symbols, `PascalCase` for classes, `UPPER_SNAKE`
  for constants. Models singular (`Ticket`, not `Tickets`).
- **TypeScript**: `PascalCase` for components and types, `camelCase` for
  functions/variables, `SCREAMING_SNAKE` for top-level constants.
- **Routes**: kebab-case paths (`/dashboard/sla-status`, `/pause-sla`).
- **DB**: `snake_case` columns and tables. Tables plural (`tickets`, `users`).
- **Enums**: PG enum NAME = python type name; values lowercase strings
  (`new`, `medium`). Every `Enum(...)` column MUST set
  `values_callable=lambda x: [e.value for e in x]` — otherwise SQLAlchemy
  writes the Python enum NAME and breaks against the PG type.

## 4. API standards

- Versioned under `/api/v1/...`. Every route belongs to an `APIRouter`
  with a `prefix` matching the resource.
- Success envelope: `{success: true, data, meta, error: null}`. Build via
  `app.schemas.envelope.ok()` or `paginated()`.
- Error envelope: `{success: false, data: null, error: {code, message, details}, request_id}`.
  Built by handlers in `app/core/exceptions.py`. Routes should raise typed
  exceptions (`ValidationError`, `NotFoundError`, `AuthorizationError`,
  `AppException`) — never return JSON error objects manually.
- Pagination params on collection GETs: `page` (≥1, default 1) and `per_page`
  (≥1, ≤100, default 20 or 50). Response carries `meta.pagination`.
- Frontend axios wrappers strip the envelope before returning to components.
  Paginated lookups go through the `unwrapPaginated` helper.
- Path UUIDs are typed `uuid.UUID` so FastAPI 422s malformed IDs.
- Every POST/PATCH/PUT/DELETE that mutates writes an `AuditLog` row.

## 5. Security

- **Authn**: JWT access + opaque refresh. Access TTL ≤ 15 min. Refresh
  rotated on every use; stolen-token reuse detected.
- **Authz**: Server-side only — never trust the client. Use `require_roles`
  or `require_permissions` per route. Branch users are scoped to their own
  tickets via `_get_ticket_or_404`.
- **Rate limiting**: Redis-backed, on every abuse-prone endpoint: auth
  (per-IP), AI (per-user), write endpoints (per-user). Fail-open on Redis
  outage but log. Returns `Retry-After` + `X-RateLimit-*` headers.
- **Passwords**: Argon2id only (`app.core.security.hash_password`).
- **PII**: PII redaction before any LLM call is a tracked open item; until
  done, do not send raw customer text to providers outside the bank network.
- **Mass assignment**: Endpoints that take `payload: dict` MUST pick fields
  by name — never `**payload` into a model. Migrating these to typed
  Pydantic request schemas is the long-term direction.
- **Tokens, secrets, keys**: Only in `backend/.env` (gitignored). Never in
  compose, never in code, never in PR descriptions.

## 6. Database

- Alembic is the source of truth. **Linear** revision graph; never delete
  or rename a revision after it lands on `main`.
- Every FK declares `ondelete=` explicitly.
- Index every column used in a WHERE/ORDER BY of a known hot query.
- Don't use `Base.metadata.create_all` outside tests/dev seeders.
- Compose `command:` currently runs `alembic upgrade head` for dev
  convenience. **Production must move this to a one-shot Job with a
  leader lock**, not the app `CMD`.

## 7. Testing

- pytest with `pytest-asyncio`, session-scoped event loop, real Postgres +
  Redis (no mocked DB).
- Conventions:
  - `test_<area>_<topic>.py` per file.
  - One assertion-of-record per test (focus, not coverage padding).
  - Drift-detector (`tests/test_frontend_contracts.py`) MUST pass — it
    greps every frontend `api.<verb>(...)` call and asserts the route exists
    with the right method on the backend.
- Don't mock SQLAlchemy. Either run against real Postgres or rewrite the
  code to be more testable.
- LLM calls are stubbed (no real Anthropic/Groq from CI).

## 8. UI/UX

- Palette tokens are in `tailwind.config.ts` ("old money" — cream paper,
  deep-forest brand, brass accent, oxblood for danger). No raw hex in
  components.
- Every async UI surface has: loading skeleton, error state with retry,
  empty state. `<Button>` uses the `loading` prop, not a custom spinner.
- Keyboard focus-visible rings are mandatory (brass, 3 px).
- Frontend never hard-codes role logic that the backend doesn't also enforce.

## 9. Git workflow

- Branch per session/feature. Never push to `main` directly.
- Commit subject ≤ 72 chars, present-tense. Body explains *why*, not *what*.
- Don't squash, rebase, or force-push branches that another agent might be
  working on. Append a new commit instead.
- Stop hook will block on untracked files — commit or gitignore everything
  before declaring "done".
- Never commit secrets, `dump.rdb`, `node_modules/`, `dist/`, or any file
  matching `.env*` (except `.env.example`).

## 10. Deployment

- Pin every image tag (`postgres:15.7-alpine`, not `:15-alpine`;
  `minio/minio:RELEASE.YYYY-MM-DD…`, not `:latest`).
- TLS terminator (nginx/Traefik) in front of backend and frontend in prod.
- `restart: on-failure:5` on the backend in prod (not `unless-stopped`) so
  the migration-loop class of bug surfaces in seconds not hours.
- Min resource limits: backend 1 GB, postgres 2 GB, redis/minio 512 MB.
- MinIO healthcheck uses `mc ready local` (image no longer ships curl).
- Frontend axios baseURL strips `/api/v1`; production must terminate TLS
  before that prefix.

## 11. Compliance checklist (before commit)

✓ Aligns with the patterns above; no new abstractions introduced for one-off use.
✓ All new endpoints carry RBAC + rate-limit decorators where relevant.
✓ Every Enum column has `values_callable`.
✓ Every new frontend api.* call has a matching backend route + correct method.
✓ Tests added for the bug + a regression test where applicable.
✓ No secrets, build artefacts, or runtime data files staged.
✓ Stop hook clean.
