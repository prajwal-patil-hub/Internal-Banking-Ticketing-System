# SUCCESS Bank — Application Workflow

This document walks through every user-facing flow in the platform —
both the **happy path** and the **negative cases** (validation errors,
authentication failures, permission denials, lockouts, rate limits, SLA
breaches, idempotency conflicts, race conditions).

All diagrams use ASCII so they render in any terminal, editor, or PR
diff. Where a ⛔ symbol appears, that branch is the negative / failure
case. ✅ marks the success branch.

---

## 0. Roles and what they can do

```
┌─────────────────┬──────────────────────────────────────────────────────┐
│ Role            │ Primary capabilities                                  │
├─────────────────┼──────────────────────────────────────────────────────┤
│ branch_user     │ Raise tickets for own branch · comment · attach ·    │
│                 │ reopen own tickets                                    │
│ agent           │ See all tickets · acknowledge · start · hold ·       │
│                 │ escalate · resolve · comment (incl. internal)        │
│ supervisor      │ All agent powers + SLA monitor · escalations ·       │
│                 │ team management                                       │
│ admin           │ All above + assign · close · user/branch/category    │
│                 │ admin · audit read                                    │
│ auditor         │ Read-only audit log · read tickets                   │
└─────────────────┴──────────────────────────────────────────────────────┘
```

Authoritative source: `backend/app/core/rbac.py`.

---

## 1. Authentication

### Happy path — login

```
   ┌──────────────┐    POST /auth/login      ┌───────────────┐
   │  Browser     │ ───────────────────────▶ │  FastAPI      │
   │  (LoginPage) │   email + password       │  RateLimit    │ ⛔ over 10/min/IP → 429
   └──────┬───────┘                          └───────┬───────┘
          │                                          │
          │                                  ┌───────▼───────┐
          │                                  │  AuthService  │
          │                                  │  .login()     │
          │                                  └───────┬───────┘
          │              ┌───────────────────────────┤
          │              │                           │
          │   ⛔ user not found / inactive            │
          │   ⛔ account locked (5 fails / 15 min)    │
          │   ⛔ wrong password (counter++, lock)     │
          │              │                           │
          │              ▼                           ▼ ✅
          │   401 AuthenticationError       1. record login_attempts
          │                                  2. reset failed_login_count
          │                                  3. update last_login_at
          │                                  4. write audit row: auth.login
          │                                  5. issue:
          │                                     - access JWT (15 min)
          │                                     - refresh token (7 d,
          │                                       hashed in DB)
          │
          ▼
   ┌──────────────┐
   │  Browser     │ ◀── { user, tokens } ──── envelope { success: true, … }
   │ stores tokens│
   │  in zustand  │
   │   + LS       │
   └──────────────┘
```

### Negative cases enumerated

| Case | Response |
|---|---|
| Missing/malformed email/password | 422 `VALIDATION_ERROR` |
| Email not in DB | 401 `UNAUTHENTICATED` "Invalid credentials." |
| Account `is_active = false` | 401 "Account inactive." |
| `locked_until > now()` | 401 "Account temporarily locked." |
| Wrong password (1–4 in a row) | 401, `failed_login_count++` |
| 5th wrong password | 401, `locked_until = now + 15min`, counter reset |
| > 10 logins / min from the same IP | 429 `RATE_LIMITED` (Redis token bucket) |

### Token refresh + rotation

```
   ┌──────────────┐  POST /auth/refresh    ┌──────────────┐
   │  Axios       │ ──────────────────────▶│  AuthService │
   │ (single-     │  raw refresh token     │  .refresh()  │
   │  flight, on  │                        └──────┬───────┘
   │   401)       │                               │
   └──────┬───────┘                               │
          │                  ⛔ token not in DB   ▼
          │                  ⛔ revoked + reused ───▶ revoke ENTIRE chain
          │                                          (theft signal)
          │                  ⛔ expired
          │                                          ▼
          │                                  ⛔ 401 → frontend clears
          │                                          session, redirects /login
          │                                          ▼
          │                            ✅ rotate: revoke old, issue new
          │                                          access + refresh pair
          ▼
   continue retried request transparently
```

### MFA enrolment

Self-service flow on `/profile`:

```
[Disabled state]    "Start enrolment"    →    POST /mfa/enroll
                                              ↓
                                              { secret, otpauth_uri }   (shown once)
                                              ↓
                                       user scans into authenticator app
                                              ↓
                                       Enter 6-digit code → POST /mfa/verify
                                              ↓
                                       ⛔ wrong code → "Invalid TOTP code"
                                              ↓ ✅
                                       mfa_enabled = true
                                       audit row: user.mfa_enabled (P15 — see runbook)

[Enabled state]     enter current 6-digit code   →   POST /mfa/disable
                                              ↓
                                       ⛔ wrong code → 422
                                              ↓ ✅
                                       mfa_enabled = false, secret cleared
```

---

## 2. Ticket lifecycle (end-to-end)

### 2.1 Create

```
   ┌────────────────────┐
   │ branch_user opens  │
   │ "+ New ticket"     │
   └─────────┬──────────┘
             │
             │ Idempotency-Key: <uuid> (frontend auto)
             ▼
   ┌───────────────────────────────────────────────┐
   │  POST /tickets                                │
   │  body: { branch_id, category_id, title,       │
   │          description, priority }              │
   └─────────┬─────────────────────────────────────┘
             │
        ┌────┴─────────────────────────────────────┐
        │                                          │
        │  ⛔ idempotency hit (same key, ≤24h)    │
        │      → return cached response, no dup    │
        │                                          │
        │  ⛔ priority not in {critical/high/      │
        │     medium/low} → 422 VALIDATION_ERROR   │
        │                                          │
        │  ⛔ branch_user trying to raise for a    │
        │     different branch_id → 422            │
        │                                          │
        │  ⛔ category_id not found → 422          │
        │                                          │
        └────┬─────────────────────────────────────┘
             │ ✅
             ▼
   ┌──────────────────────────────────────────────┐
   │ TicketService.create()                       │
   │  1. allocate ticket_no = TKT-YYYY-NNNNNN     │
   │     via Postgres sequence                    │
   │  2. INSERT tickets row, status=new           │
   │  3. SLAEngine.on_ticket_created()            │
   │     - reads sla_policies for priority        │
   │     - INSERT sla_tracking                    │
   │       due_at = now + resolution_minutes      │
   │       response_due_at = now + response_min   │
   │  4. AuditService.log("ticket.created")       │
   │  5. NotificationService.dispatch(admins,     │
   │     TICKET_CREATED, in-app)                  │
   │  6. cache success response by Idempotency-Key│
   └──────────────────────────────────────────────┘
```

### 2.2 Workflow transitions (state machine)

Allowed transitions are codified in `app/models/enums.py` →
`ALLOWED_TRANSITIONS`. Every transition through `WorkflowService` is:

1. Authorized (RBAC dependency on the route).
2. Legal under the matrix.
3. Logged to the audit trail.
4. Where relevant: notified, escalation-raised, SLA-paused.

```
                              ┌──────────┐
                              │   new    │  (created by branch_user)
                              └────┬─────┘
                                   │ acknowledge (admin)
                                   ▼
                              ┌────────────┐
                              │acknowledged│
                              └────┬───────┘
                          assign  │
                  ┌───────────────┴───────────────┐
                  │                               │
                  ▼                               ▼
            ┌──────────┐                  ┌─────────────┐
            │ assigned │ ◀───────────────│ in_progress │ ─┐
            └────┬─────┘                  └──────┬──────┘  │
              start  │                            │         │
                  │     ┌── hold ─────────┐       │         │
                  │     ▼                 │       │         │
                  │  ┌─────────┐          │       │         │
                  └─▶│ on_hold │ resume───┘       │         │
                     └────┬────┘                  │         │
                          │ escalate              │ escal.  │ resolve
                          ▼                       ▼         ▼
                     ┌──────────┐           ┌──────────┐ ┌──────────┐
                     │escalated │──resolve▶ │          │ │ resolved │
                     └─────┬────┘           └──────────┘ └────┬─────┘
                           │                                  │ close (admin)
                           │                                  ▼
                           │                              ┌────────┐
                           │                              │ closed │
                           │                              └────┬───┘
                           │                                   │ reopen
                           └─────────────┐                     │
                                         ▼                     │
                                   ┌──────────┐                │
                                   │ reopened │◀───────────────┘
                                   └──────────┘
                                         │ assign / start
                                         ▼
                                       (cycle continues)
```

### 2.3 Negative-case matrix for transitions

| Action | Negative case | Response |
|---|---|---|
| Acknowledge | Current status not `new` | 409 `CONFLICT` "Cannot transition from X to acknowledged" |
| Assign | Both user_id and team_id null | 422 "Provide assigned user, team, or both." |
| Assign | Ticket in `resolved` / `closed` | 409 "Cannot be (re)assigned in its current state." |
| Start work | Not in {acknowledged, assigned, on_hold, escalated, reopened} | 409 transition rejected |
| Hold | Not in {assigned, in_progress} | 409 transition rejected |
| Escalate | Not in {assigned, in_progress, on_hold} | 409 transition rejected |
| Resolve | Not in {in_progress, escalated} | 409 transition rejected |
| Close | Not in `resolved` | 409 transition rejected |
| Reopen | Not in {resolved, closed} | 409 transition rejected |
| Any transition | Caller lacks the RBAC permission code (e.g. branch_user calling /assign) | 403 `FORBIDDEN` `{missing: ["ticket.assign"]}` |
| Any | Caller is branch_user and ticket is from a different branch | 404 `NOT_FOUND` (we don't disclose existence) |

### 2.4 Comments

```
   POST /tickets/{id}/comments  { body, is_internal }
                │
                ▼
   ┌─────────────────────────────────────────┐
   │ ⛔ body empty / > 10_000 chars → 422     │
   │ ⛔ branch_user + is_internal=true → 422  │
   │    "Branch users cannot post internal." │
   │ ⛔ no ticket.comment permission → 403    │
   │ ⛔ no ticket.comment_internal but        │
   │    is_internal=true → 422                │
   └────────────────────┬────────────────────┘
                        │ ✅
                        ▼
   ┌─────────────────────────────────────────┐
   │ WorkflowService.add_comment()           │
   │  1. INSERT ticket_comments               │
   │  2. If first agent reply:                │
   │     - set tickets.first_response_at      │
   │     - SLAEngine.on_first_response()      │
   │       (clears response_due_at)           │
   │  3. AuditService.log("comment.posted")   │
   └─────────────────────────────────────────┘

   GET /tickets/{id}/comments
                │
                ▼
   branch_user → returns only is_internal=false rows
   everyone else → returns all comments
```

### 2.5 Attachments

```
   POST /tickets/{id}/attachments  (multipart, single file)
                │
                ▼
   ┌─────────────────────────────────────────┐
   │ ⛔ content_type not in allowlist → 422   │
   │    (png/jpg/gif/webp/pdf/txt/csv/json/  │
   │     zip/xlsx/docx)                       │
   │ ⛔ size > 10 MB → 422                    │
   │ ⛔ no ticket.attach permission → 403     │
   │ ⛔ ticket not visible to caller → 404    │
   └────────────────────┬────────────────────┘
                        │ ✅
                        ▼
   1. StorageAdapter.put_attachment() → MinIO/S3
      key = tickets/{ticket_id}/{uuid}_{file_name}
      Metadata.sha256 = SHA-256(body)
   2. INSERT attachments row
   3. response: { id, file_name, mime_type, size_bytes, checksum_sha256 }
```

---

## 3. SLA engine + escalation chain

```
   Every 60 seconds, APScheduler (Redis-locked, single instance):
   ─────────────────────────────────────────────────────────────
              │
              │ acquire Redis SET NX lock "success-bank:sla:lock"
              │   (TTL 50s — releases on its own if instance dies)
              │
              │  ⛔ another instance holds it → skip this tick
              │
              ▼ ✅
   ┌─────────────────────────────────────────────────────────────┐
   │ SLAEngine.detect_breaches()                                  │
   │   1. SELECT sla_tracking JOIN tickets WHERE                  │
   │        due_at <= now()                                       │
   │        AND breached = false                                  │
   │        AND paused_at IS NULL                                 │
   │        AND tickets.status NOT IN (resolved, closed)          │
   │   2. UPDATE sla_tracking SET breached=true, breach_at=now()  │
   │   3. Same scan for response_breached                         │
   └────────────────────┬────────────────────────────────────────┘
                        │
                        ▼
   ┌─────────────────────────────────────────────────────────────┐
   │ For each breached ticket:                                    │
   │  EscalationService.raise_for_breach()                        │
   │    - idempotent: skips if an unresolved auto-escalation      │
   │      already exists for this ticket                          │
   │    - INSERT escalations row (level=1, is_automatic=true)     │
   │    - NotificationService.dispatch(                           │
   │        user_ids=supervisors,                                 │
   │        type=SLA_BREACHED,                                    │
   │        channels=[in_app, email])                             │
   │    - implicit audit via row insert + notification log        │
   └─────────────────────────────────────────────────────────────┘

   Pause / resume:
   ─────────────────────────────────────────────────────────────
   - Transition to on_hold → SLAEngine.on_paused() stamps paused_at
   - Transition out of on_hold → SLAEngine.on_resumed() adds the
     elapsed pause to total_paused_seconds and pushes due_at forward
     by the same amount

   Reopen:
   ─────────────────────────────────────────────────────────────
   - SLAEngine.on_reopened() resets due_at + response_due_at fresh
     from the policy, clears breached + response_breached flags
```

### Manual escalation by an agent

```
   POST /tickets/{id}/escalate  { reason }
              │
              ▼
   ⛔ status not in {assigned, in_progress, on_hold} → 409
   ⛔ no ticket.escalate permission → 403
              │ ✅
              ▼
   WorkflowService.escalate()
     1. set status = escalated
     2. INSERT ticket_comments (is_internal=true, body=[Escalated] reason)
     3. EscalationService.raise_manual()
        - level = (previous open escalation's level + 1) or 1
        - INSERT escalations (is_automatic=false)
     4. NotificationService.dispatch(supervisors, ESCALATION_RAISED)
     5. AuditService.log("ticket.escalated")
```

---

## 4. Notification fan-out

```
   Trigger event             Recipients                Channels
   ──────────────────────────────────────────────────────────────
   ticket.created            all active admins         in_app
   ticket.assigned           the new assignee          in_app + email
   ticket.resolved           the raiser                in_app + email
   sla.breached (auto)       all active supervisors    in_app + email
   escalation.raised (man.)  all active supervisors    in_app + email

   NotificationService.dispatch(user_ids, type, channels)
        │
        ▼
   For each (user × channel):
     1. INSERT notifications row, status="pending"
     2. Call channel adapter:
          - in_app  → no-op (the row IS the in-app message)
          - email   → SMTP (MailHog in dev, SES/SendGrid in prod)
          - sms     → logging stub (Twilio in prod)
     3. UPDATE notifications.status = "sent" | "failed"
                          .sent_at = now() (on success)

   ⛔ SMTP failure → row stays status="failed"; the persisted row IS
                     the source of truth so a worker can retry later.
```

### Frontend bell behaviour

```
   Topbar bell polls GET /notifications/unread-count every 30s.
   Click opens dropdown → GET /notifications (latest 12, in_app).
   Click row →
       1. POST /notifications/{id}/read (idempotent)
       2. navigate to /tickets/{payload.ticket_id} if present
   "Mark all read" → POST /notifications/mark-all-read (bulk)
```

---

## 5. Audit trail

```
   Every state-changing service call invokes AuditService.log(…).
   AuditService reads context from a ContextVar populated by
   AuditContextMiddleware:
     - request_id (correlation id, also in X-Request-ID response header)
     - client_ip
     - user_agent

   INSERT audit_logs (
     actor_user_id, actor_role, entity_type, entity_id,
     action, old_value (JSONB), new_value (JSONB),
     ip_address, user_agent, request_id, created_at
   )

   audit_logs is APPEND-ONLY at the database level:

       ┌────────────────────────────────────────────────────────┐
       │ CREATE TRIGGER trg_audit_logs_no_update                │
       │   BEFORE UPDATE ON audit_logs                          │
       │   FOR EACH ROW EXECUTE FUNCTION audit_logs_immutable();│
       │                                                        │
       │ CREATE TRIGGER trg_audit_logs_no_delete                │
       │   BEFORE DELETE ON audit_logs … (same function)        │
       │                                                        │
       │ Function raises: 'audit_logs is append-only'           │
       └────────────────────────────────────────────────────────┘

   ⛔ Any attempted UPDATE or DELETE — by app code, by a DBA, by an
      adversary with credentials — fails at the database. Removing
      the trigger to bypass is itself an auditable event in
      pg_stat_activity / pg_event_trigger logs.
```

---

## 6. Admin flows

### 6.1 User CRUD

```
                                 ┌─ create  → POST /users
                                 │             ⛔ duplicate email → 409
                                 │             ⛔ unknown role → 422
                                 │             ✅ creates user, optionally
                                 │                returns one-time password
                                 │
   /users (admin only) ──────────┤── edit    → PATCH /users/{id}
                                 │             ⛔ user not found → 404
                                 │
                                 ├─ reset    → POST /users/{id}/reset-password
                                 │             ✅ generates new password
                                 │             ✅ revokes ALL open refresh
                                 │                tokens for that user
                                 │             ✅ surface password once via UI
                                 │
                                 ├─ deactivate → DELETE /users/{id}
                                 │             ⛔ self-deactivation → 409
                                 │             ✅ is_active = false
                                 │
                                 └─ restore   → POST /users/{id}/restore
```

### 6.2 Branch / Category / Team management

Identical pattern: soft-delete on DELETE, restore endpoint, edit via
PATCH. Hard delete is intentionally unavailable so foreign keys on
existing tickets / audit rows stay intact.

Teams add: `GET/POST/DELETE /teams/{id}/members/{user_id}` for
agent / supervisor membership.

---

## 7. Rate limits

```
   /auth/login                  10 requests / minute / IP
   any non-GET (auth'd)         120 requests / minute / actor
                                  (or IP if anonymous)

   Backed by Redis fixed-window counter.

   ⛔ Over the limit → 429 RATE_LIMITED with envelope:
      {
        "code": "RATE_LIMITED",
        "message": "Too many requests.",
        "details": { "retry_after_seconds": <ttl> }
      }
      and HTTP header `Retry-After: <ttl>`.

   Exempt: /healthz, /readyz, /api/docs, /api/openapi.json, /metrics.
```

---

## 8. Frontend session lifecycle

```
   ┌────────────┐   no token / 401 cleared    ┌──────────────┐
   │  /login    │ ─────────────────────────▶  │ /dashboard   │
   └─────┬──────┘  (RequireAuth redirects)    └──────┬───────┘
         │                                            │
         │  ✅ login → setSession()                   │
         │     - access_token   (localStorage)        │
         │     - refresh_token  (persisted zustand)   │
         │     - user           (persisted zustand)   │
         │                                            │
         │                                            ▼
         │                                  Axios attaches Bearer
         │                                  header on every request
         │                                            │
         │             ┌──────────────────────────────┤
         │             │                              │
         │             │ Response 401 (token expired) │
         │             ▼                              ▼
         │  Single-flight refresh:           Response 2xx → render
         │     POST /auth/refresh
         │       ✅ → retry original req with new token
         │       ⛔ → clear session, dispatch
         │            "auth:logout" CustomEvent
         │            → RequireAuth sees no token, redirects /login
         │
         ▼
   user clicks Sign out → POST /auth/logout, clear session, redirect.
```

---

## 9. CSV export + idempotency keys (operations specifics)

```
   Tickets export:
   GET /tickets/export.csv?<same filters as list, no pagination>
       ↓
   StreamingResponse, returns up to 10 000 matching rows.
   Branch-scoped for branch_user; role-gated visibility unchanged.

   Audit export:
   GET /audit-logs/export.csv?<filters>
       Requires audit.read permission.
       Diffs serialised inline as JSON.

   Idempotency on POST /tickets:
   Client sends `Idempotency-Key: <uuid>`.
       ↓
   Server checks Redis idem:{actor_id}:{key}.
       hit (≤24h) → return cached envelope, no new ticket
       in-flight  → 409 "Duplicate request — retry shortly."
       miss       → reserve key (30s TTL), run handler, cache the
                    success response (24h TTL). On failure, release the
                    reservation so the client can retry cleanly.
```

---

## 10. Deploy / infra view

```
       (browser)
           │ http
           ▼
   ┌───────────────┐
   │     nginx     │  ← TLS termination + reverse proxy in prod compose
   └──────┬────────┘
          ├── /        → frontend container (Vite-built static SPA)
          ├── /api/*   → backend container (uvicorn FastAPI workers)
          └── /metrics → backend (RFC1918 allowlist)
                  │
   ┌──────────────┼─────────────────────────────────┐
   ▼              ▼                                 ▼
postgres      redis (rate-limit                MinIO (S3-compat)
  ↑              ↑  scheduler lock,             ↑   ticket attachments
  │              │  idempotency cache)          │
  │              │                              │
  └──────────────┴──────────────────────────────┘
                APScheduler ticks every 60s
                inside the backend process,
                lock-guarded so only one
                replica scans per minute.
```

---

## 11. Glossary of negative-path response codes

| HTTP | Code in envelope | Meaning |
|---|---|---|
| 401 | `UNAUTHENTICATED` | Bearer missing / token invalid / token expired / refresh-token reuse detected |
| 403 | `FORBIDDEN` | Authenticated but missing role / permission |
| 404 | `NOT_FOUND` | Resource doesn't exist *or* caller can't see it (branch-scoped) |
| 409 | `CONFLICT` | Invalid state transition, idempotency in-flight, duplicate-code on branch / user, self-deactivation |
| 422 | `VALIDATION_ERROR` | Pydantic validation failure (`details.errors`) or business-rule violation |
| 429 | `RATE_LIMITED` | Token-bucket exceeded; `Retry-After` header set |
| 500 | `INTERNAL_ERROR` | Anything not matched above — always logged with full stack, never leaked to client |

Every error response carries the same shape:
```json
{
  "success": false,
  "data": null,
  "error": { "code": "…", "message": "…", "details": { … } },
  "request_id": "…"
}
```
so the frontend can use a single `extractError()` helper everywhere.
