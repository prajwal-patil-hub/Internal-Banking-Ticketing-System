# Feature Ticket List

Work not yet done, as of `c554e3c`. Each ticket says what is wrong now, what
done looks like, and how to prove it — because "add rate limiting" is not a
ticket anyone can close honestly.

Sizes: **S** ≈ half a day · **M** ≈ 1–2 days · **L** ≈ 3+ days.

---

## P0 — Do before this handles real data

### SEC-1 · Make the audit trail actually immutable · M

**Now.** Every state change writes an `audit_logs` row and the application only
ever inserts. But there is no database trigger and no revoked grant, so
anything holding the connection string can rewrite or delete history. For a
system whose primary value is its audit trail, this is the largest gap.

**Done when**
- A migration adds a `BEFORE UPDATE OR DELETE ON audit_logs` trigger that
  raises.
- `REVOKE UPDATE, DELETE ON audit_logs` from the application role.
- A test asserts that an UPDATE and a DELETE both fail.
- The runbook says how to correct a bad row (append a correcting entry — never
  edit).

**Watch for:** `pg_restore` must still be able to load the table. Test the
restore drill after this lands.

---

### SEC-2 · Resolve the two role definitions · S

**Now.** `core/rbac.py` defines `Role`, `Permission`, `ROLE_PERMISSIONS`, and
`db/seed.py` writes them into `permissions` and `role_permissions`. **Nothing
reads those tables at request time.** Enforcement is `role.name` against
hardcoded sets in `core/authz.py`. `require_permissions()` exists and is used
by no route.

Access is not wrong today. The risk is that someone reasonably assumes editing
`role_permissions` changes what people can do.

**Done when** either:
- (a) the tables drive enforcement and `require_permissions` replaces
  `require_roles`, with the RBAC matrix re-run against it; **or**
- (b) `core/rbac.py`, both tables and their seed are deleted, and `authz.py` is
  documented as the only source.

**Recommend (b)** unless per-permission grants are actually wanted. Two sources
of truth where one is decorative is the worst of both.

---

### OPS-1 · TLS · M

**Now.** Nothing in the stack terminates TLS. Credentials and ticket bodies —
which may contain account numbers — cross the network in plaintext.

**Done when** a terminating proxy is in front, HTTP redirects to HTTPS, HSTS is
set, and the runbook covers certificate renewal.

---

## P1 — Before more than one backend replica

### OPS-2 · Move the schedulers out of the API process · M

**Now.** The SLA worker (5 min) and email worker (2 min) are APScheduler jobs
inside the API process. Two replicas run two schedulers: duplicate escalations,
duplicate emails, the same inbound message processed twice.

**Done when** either a Redis/Postgres advisory leader lock guards both jobs, or
they run as a separate single-replica worker container.

**Done means proven:** two backend replicas up, one breach detected, exactly
one escalation event written.

---

### SEC-3 · General rate limiting · M

**Now.** Only the AI routes are limited. `/auth/login` is not — account lockout
bounds guessing per account, but nothing bounds requests per IP, so credential
stuffing across many accounts is unthrottled.

**Done when** a middleware limits by IP and by user, `/auth/*` has a stricter
bucket, limits return `429` with `Retry-After`, and a test proves login is
throttled.

---

### OPS-3 · Scheduled backups · S

**Now.** `backup.py` works and the restore is drilled, but nothing runs it. A
backup nobody takes is a script, not a backup.

**Done when** a scheduled job runs it with `--keep`, writes off-host, alerts on
failure, and the runbook records where sets live and who checks them.

**Non-obvious:** the failure to catch is not a corrupt dump — it is nobody
noticing the bucket credentials changed six weeks ago. Alert on *absence* of a
recent successful set.

---

## P2 — Quality and correctness

### QA-1 · Make mypy a gate · L

**Now.** Advisory. ~278 errors under `strict`, ~190 of them `dict` without type
parameters. Substantive ones are already fixed.

**Done when** `disallow_any_generics` and `disallow_untyped_calls` are relaxed
(leaving ~39), those are worked down, and `|| true` is removed.

**Do it in that order.** Turning it on at 278 blocks every unrelated change,
which is how a gate gets deleted rather than met.

---

### QA-2 · Page-level frontend tests · M

**Now.** 42 tests cover helpers, `FileStager`, upload orchestration and auth
refresh. No page renders in a test.

**Done when** TicketDetailPage, DashboardPage and CreateTicketPage have tests
with a mocked query client.

**The one that matters most:** assert that an internal comment's attachments
never render for a branch user. That rule is proven server-side; the client
should not be the only thing standing between a wrong API response and a leak.

---

### QA-3 · Uniform repository layer · M

**Now.** Parts of `tickets.py` talk to the ORM directly. This is exactly why
the state machine went unenforced: `VALID_TRANSITIONS` lived in `TicketService`
and the HTTP path never called it.

**Done when** ticket routes go through `TicketService`, with no bare
`select(Ticket)` in the route module.

---

### FEAT-1 · Email intake against a real mailbox · S

**Now.** Parse → thread → deduplicate → ticket is proven, but only by driving
`process_inbound_email()` directly. Mailpit is SMTP-only and cannot feed the
poller, so `IMAP_ENABLED` has never been true against a real server.

**Done when** a real mailbox is configured, a sent message becomes a ticket, a
reply becomes a comment on the same one, and a re-poll creates nothing.

---

### FEAT-2 · Verify attachments against real MinIO · S

**Now.** Exercised against an S3-compatible stand-in, never the actual MinIO
container.

**Done when** upload, download, delete and the 503-on-storage-down path are
confirmed against `infra/docker-compose.yml`'s MinIO, and a `docker compose
down -v` followed by a first upload creates the bucket cleanly.

---

## P3 — Worth doing, not urgent

### FEAT-3 · Malware scanning · L

Executables and archives are refused because there is no scanner. With ClamAV
in the stack, scan on upload, quarantine on hit, and the accepted-type list can
widen.

### FEAT-4 · Retention and archival · M

Nothing ages out. Tickets, audit rows, AI logs and attachments grow forever.
Needs a policy per data class — and the audit trail's policy is a compliance
question, not an engineering one.

### FEAT-5 · Field-level encryption for ticket bodies · L

Bodies may contain account numbers and are stored in plaintext. Encrypting at
rest costs full-text search over them; decide which matters more.

### FEAT-6 · PII redaction before the model · M

The grounding block sends ticket text to Ollama. Local today, so it does not
leave the host — but the moment `LLM_BASE_URL` points anywhere else, it does.
Redact account and card numbers before they enter the prompt.

### UX-1 · Accessible name for the file input · S

Hidden and opened by a visible button, so it has no name of its own. Fine for
mouse and for the button's keyboard path; worth fixing if it must be reachable
directly.

### OPS-4 · Use Redis or drop it · S

It runs in compose, is a declared dependency and is configured — and **no
application code imports it**. A service nothing talks to is a thing to patch,
monitor and restore for no benefit.

OPS-2 (scheduler lock) and SEC-3 (rate limiting) both want exactly this. Do
either and Redis earns its place; do neither and remove it.

### DOC-1 · Retire the stale architecture note · S

`docs/architecture.md` describes `core/rbac` as the enforcement point,
`services/sla_engine`, a `notifications` table, an SSE notification fan-out and
a 60-second scheduler. **None of those exist.** `02-technical-architecture.md`
replaces it; delete or clearly mark the old one.

---

## Sequencing

```
SEC-1 ─┐
SEC-2 ─┼─► P0: before real data
OPS-1 ─┘
          OPS-2 ─┐
          SEC-3 ─┼─► P1: before scaling out
          OPS-3 ─┘
                   QA-1, QA-2, QA-3, FEAT-1, FEAT-2 ─► P2
                                                        P3: as capacity allows
```

FEAT-1 and FEAT-2 are cheap and close the two "never verified against real
infrastructure" caveats — worth pulling forward if that infrastructure is
already to hand.
