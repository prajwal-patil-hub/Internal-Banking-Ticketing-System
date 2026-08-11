# Security & Access

**Status: as-built at `c554e3c`.** Every control below was checked against the
code. Gaps are listed as gaps.

---

## 1. The access model, in one paragraph

One role per user, from the `roles` table, enforced at request time by
`require_roles(...)` in `app/api/v1/deps.py` and the guards in
`app/core/authz.py`. `is_super_admin` is a boolean on the user, not a role.
Visibility of *data* is separate from permission to *act*, and is decided by
the org-unit tree.

### Two sources of truth, one of which does nothing

`core/rbac.py` defines `Role`, `Permission` and `ROLE_PERMISSIONS`, and
`db/seed.py` writes them into the `permissions` and `role_permissions` tables.

**Nothing reads those tables at request time.** Enforcement is entirely
`role.name` against a hardcoded set. `require_permissions()` exists in `deps.py`
but no route uses it.

The risk is not that access is wrong today — it is that a reviewer or a future
change may reasonably assume editing `role_permissions` changes what people can
do. It does not. Either wire the tables in or delete them; leaving both is the
worst option.

## 2. Roles

| Role | Tickets | Users / org | Audit | Escalation queue |
|---|---|---|---|---|
| `branch_user` | Own only — raise, comment, attach, close/reopen | — | — | — |
| `agent` | Any in scope — assign, progress, resolve, attach, AI helpers | — | — | — |
| `supervisor` | As agent | Read directory | — | Yes |
| `admin` | As agent | Full | Yes | Yes |
| `auditor` | **Read only** | — | Yes | — |

`TICKET_WRITE_ROLES` is `{agent, supervisor, admin}`. **`auditor` is
deliberately absent** — it was once inside this set and silently held write
access to every ticket while being documented as read-only.

`is_super_admin` does **not** override read-only. A read-only role holder
marked super admin is still an auditor.

### Privilege escalation, closed

- **Only a super admin can grant super admin.** Without this, an ordinary admin
  could create an account with the flag, choose its password, and hold full
  control in two calls.
- **Only a super admin can modify a super admin** — otherwise any admin could
  reset the super admin's password and take the account over.

Both live in `core/authz.py` (`assert_can_grant_super_admin`,
`assert_can_manage_user`) and are covered by the RBAC test matrix.

## 3. Data visibility

Acting rights say *what* you may do; visibility says *which rows*.

1. **Super admin** — everything.
2. **Org-scoped user** — tickets in their accessible org subtree, plus anything
   assigned to them.
3. **Branch user without an org unit** — only tickets they raised.
4. **Everyone else** — unrestricted within their role.

The same filter is applied by the REST list endpoints, the single-ticket
fetch, and the AI grounding service. **The assistant cannot see more than the
user can** — point it at a ticket outside scope and it is told the ticket is
unavailable: no title, no number, nothing.

## 4. Authentication

| Control | Setting |
|---|---|
| Password hashing | Argon2id (`argon2-cffi` defaults: t=3, m=64 MB, p=4) + pepper |
| Rehash on login | Yes, when parameters change |
| Lockout | 5 consecutive failures → 15 minutes |
| Access token | JWT, 15 minutes, stateless |
| Refresh token | 256-bit random, **only the SHA-256 hash stored**, 7 days |
| Refresh rotation | Presenting one revokes it and issues a new one |
| Reuse detection | Reusing a revoked refresh token revokes the **entire chain** |
| Login attempts | Every attempt recorded with IP, user agent and reason |

**Rotating `PASSWORD_PEPPER` invalidates every stored hash.** Nobody can sign
in and every account needs a reset. Set it once, before the first user exists.

## 5. Multi-factor authentication

Available to **any** user (not restricted by role, contrary to the older
architecture note).

- Enrolment is two-step: `/mfa/setup` stores a secret but leaves MFA **off**;
  only a correct code at `/mfa/enable` turns it on. A one-step enable would
  lock out anyone whose authenticator failed to scan.
- The challenge token between password and code is typed `mfa`, not `access`,
  so `get_current_user` rejects it — a half-authenticated session reaches
  nothing.
- Wrong codes increment the **same lockout counters** as a wrong password, so
  guessing is bounded rather than unlimited.
- Disabling MFA requires the account password, not just a live session —
  otherwise a stolen access token strips the second factor.

### Recovery codes

Ten, issued at enrolment, shown exactly once.

- Stored as **SHA-256 hashes only**, so they cannot be re-displayed and a
  database leak does not hand over working credentials.
- SHA-256 rather than Argon2 deliberately: the input is ~50 bits of CSPRNG
  output, so there is no dictionary to slow down, and verification scans the
  user's unused codes on every attempt.
- Spending one **marks it used rather than deleting it**, so "a recovery code
  was consumed at 09:14" stays answerable after an incident.
- Replay fails. Regenerating requires the password, since it invalidates codes
  the real owner may be holding.

## 6. Attachments

The highest-risk surface, because it accepts bytes from users.

| Control | Behaviour |
|---|---|
| Size | 15 MB, enforced server-side |
| Types | Images, PDF, text, CSV, Office only |
| Executables / archives | **Refused outright** — there is no malware scanner, and an unscanned archive is the classic delivery route |
| Filenames | Sanitised; directory components stripped, so `../../etc/passwd` becomes `passwd` |
| Storage keys | `tickets/<id>/<uuid>.<ext>` — a leaked key reveals nothing, and two uploads of `statement.pdf` never collide |
| Delivery | `Content-Disposition: attachment` always, so nothing renders inline |

**Files stream through the API, never via presigned URLs.** A presigned URL is
a bearer token in a query string: it outlives the session, survives in browser
history and proxy logs, and grants access to anyone holding it. Every read goes
through the ticket permission check instead.

### The internal-note rule

**A file attached to an internal comment is as invisible as the comment.**

Filtering the note while still serving its attachment would leak exactly what
the flag exists to withhold — and the file is usually the sensitive part.
Enforced in both the listing and the download, and the download answers **404
rather than 403**, so the response does not confirm that a hidden note exists.

Related: an agent cannot attach a file to *someone else's* comment. Without
that check, a file could be hung off the customer's own message where it would
read as something they had sent.

## 7. Audit trail

Every state change writes actor id, actor email, actor role, action, entity,
before/after values, IP, user agent and request id.

**Gap — immutability is convention only.** The application only inserts, but
there is no database trigger and no revoked UPDATE/DELETE grant. Anything with
the connection string can rewrite history. For a system whose primary value is
its audit trail, this is the most significant open item.

Suggested fix: a `BEFORE UPDATE OR DELETE` trigger on `audit_logs` that raises,
plus `REVOKE UPDATE, DELETE ON audit_logs` from the application role.

## 8. Transport and secrets

- **Nothing terminates TLS.** A reverse proxy or load balancer must sit in
  front before this is reachable from anywhere untrusted.
- Security headers are set by nginx with `always`, so they survive error
  responses: `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`,
  `Referrer-Policy`, `Permissions-Policy`.
- Production compose declares every secret with `${VAR:?}`, so a missing one
  **stops the deploy** rather than falling back to a development default.
- `.dockerignore` excludes `.env`. Without it the file the README tells every
  developer to create — JWT secret, pepper, database and S3 credentials — is
  copied into the image, where `docker history` shows it to anyone who can pull.
- Only the web tier publishes a port. Postgres, Redis and MinIO are reachable
  on the internal network and nowhere else.

## 9. What is not protected

Stated plainly so nobody assumes otherwise:

- **No TLS** in the stack.
- **No malware scanning** of uploads.
- **No general rate limiting.** The AI routes have one; nothing else does.
- **No CSRF tokens** — mitigated by bearer tokens in headers rather than
  cookies, but worth revisiting if auth ever moves to cookies.
- **No field-level encryption.** Ticket bodies may contain account numbers and
  are stored in plaintext.
- **No secret rotation mechanism.** Rotating means editing the environment and
  restarting.
- **No PII redaction** in logs or in what is sent to the model.

## 10. Recovering access

| Situation | Route |
|---|---|
| Locked out (5 failures) | Wait 15 minutes, or clear `locked_until` |
| Lost authenticator, has codes | Any unused recovery code works at sign-in |
| Lost authenticator, no codes | Admin clears enrolment: `POST /users/{id}/mfa/reset` |
| Lost the only super admin | **No API path by design.** Set `is_super_admin` directly on the row |
