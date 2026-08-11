# Runbook — SUCCESS Bank Internal Ticketing

Operational procedures: what to run, what breaks, and how to tell the
difference. Written from failures actually encountered building this system,
not from a template — the symptoms below are ones that have really appeared.

For architecture see [`architecture.md`](architecture.md); for a feature tour
see the *Walking the system* section of the [README](../README.md).

---

## Health

| Check | Command | Healthy answer |
|---|---|---|
| API alive | `curl localhost:8000/api/v1/healthz` | `{"status":"alive"}` |
| API ready (DB reachable) | `curl localhost:8000/api/v1/readyz` | 200 |
| AI assistant | `curl -H "Authorization: Bearer <t>" localhost:8000/api/v1/ai/health` | `reachable: true`, `model_available: true` |
| Schema matches models | `alembic check` | no `add_/remove_table` or `_column` |

`healthz` answers while the database is down — it only proves the process is
up. Use `readyz` when the question is "can it serve requests".

---

## Backup and restore

**A ticket's attachments live in two places.** The row, filename and checksum
are in Postgres; the bytes are in object storage. A database-only backup
restores to a system where every attachment lists correctly and fails on
download — worse than an obvious outage, because it looks healthy. Both scripts
treat the pair as one unit and refuse half of it.

### Taking a backup

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python scripts/backup.py --out /backups --keep 14
```

Produces `/backups/<timestamp>/` containing `database.dump`, `objects/`, and a
`manifest.json` with row counts taken at dump time. `--keep N` prunes older
sets after a successful run.

If object storage is unreachable the run **fails and deletes the partial set**.
That is deliberate: the newest surviving set is always one that completed.

### Restoring

```bash
docker compose -f infra/docker-compose.yml exec backend \
  python scripts/restore.py /backups/20260811T020304Z
```

**This replaces the current database.** `pg_restore --clean` drops what it is
about to recreate. The prompt is the guard; `--yes` skips it for automation.

The script verifies before reporting success: row counts against the manifest,
and every attachment row checked to have its object present. If either fails it
exits non-zero and says which.

### Drill it

A backup you have never restored is a hypothesis. Against a scratch copy:

```bash
# 1. back up
python scripts/backup.py --out /tmp/drill

# 2. destroy both stores
psql "$PG_URL" -c "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"
#    ...and empty the bucket

# 3. restore and verify
python scripts/restore.py /tmp/drill/<timestamp> --yes
```

This exact sequence was run against a seeded database: 56 tickets, 24 comments,
15 attachments. After restore, attachments downloaded through the API with
checksums identical to before the backup.

Do this on a schedule. The failure you are looking for is not "the dump is
corrupt" — it is "nobody noticed the bucket credentials changed six weeks ago".

---

## Deploying

```bash
docker compose -f infra/docker-compose.yml build
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml exec backend alembic upgrade head
```

Migrations run as a separate step, not on container start: two backend
replicas booting together would otherwise race on the same migration.

**Back up before migrating.** Some migrations drop columns; `0006` drops four.
There is no undo beyond a restore.

### Rolling back

Application only — code back, schema forward:

```bash
docker compose -f infra/docker-compose.yml up -d --no-deps backend=<previous-tag>
```

Safe when the migration was additive. If the release dropped or narrowed a
column, the old code will fail against the new schema; either roll the schema
back too (`alembic downgrade -1`, which every migration here supports) or
restore from backup.

---

## Failure modes

### The AI assistant says it cannot connect

`GET /api/v1/ai/health` reports what is wrong in plain English. Common causes:

- **Ollama not running.** Start it; the endpoint reports `reachable: false`.
- **Model not pulled.** `model_available: false` — run `ollama pull glm4`.
- **`LLM_MODEL` set to `LLM_MODEL=glm4:latest`.** A real mistake made here: the
  variable name got included in its own value. The health endpoint detects an
  `=` in the model name and says so.
- **macOS: Ollama bound to `127.0.0.1`.** The Docker VM cannot reach it. Run
  `launchctl setenv OLLAMA_HOST 0.0.0.0` and restart Ollama.

The system degrades rather than failing: tickets still get created from email
without AI extraction, carrying the subject and raw body.

### Attachment upload returns 503

`STORAGE_UNAVAILABLE` means MinIO/S3 is unreachable — not a bad request.
Check the `minio` container and `S3_ENDPOINT_URL`. Nothing is lost; the ticket
or reply exists and the file can be attached again once storage is back.

### SLA breaches are not escalating

The SLA worker runs every 5 minutes and evaluates escalation rules on breach.
Check for `sla_worker_started` at boot and `sla_breaches_detected` since. If
the worker started but nothing escalates, the likely cause is no matching
escalation rule — the worker logs `sla_breach_not_escalated` with a reason.

A ticket will not escalate twice for the same trigger; that is intentional
suppression, not a stall.

### Inbound email is not creating tickets

- `IMAP_ENABLED=false` is the default — the worker logs `email_worker_disabled`
  at boot and does nothing.
- **Mailpit cannot feed it.** Mailpit is an SMTP sink with no IMAP server; it
  catches what the system *sends*. Inbound needs a real mailbox.
- To test parsing without a mailbox, drive `EmailService.process_inbound_email()`
  directly — see the README.

### Dashboard numbers disagree with the list a card opens

This should not happen; the pairing is asserted in `tests/test_kpi_drilldowns.py`
and every card was checked against its drill-down. If it recurs, the cause is
almost certainly a definition written out twice — the historical instances were
six competing definitions of "open" and a risk threshold duplicated between the
tile and the filter. Both are now single constants in `app/models/ticket.py`.

### `alembic check` reports no drift but the schema is wrong

Confirm `alembic/env.py` still imports `app.models`. Without it `Base.metadata`
is empty, autogenerate proposes dropping the whole schema, and the check reports
nothing no matter how far the models have moved. That is how `inbound_emails`
came to be missing eleven columns.

---

## Credentials

Demo accounts and their passwords are in the README. They exist for the seeded
demo only.

**Before any real deployment**, replace: `JWT_SECRET` (32+ random characters),
`PASSWORD_PEPPER`, the Postgres password, the MinIO keys, and every seeded
account password. `docker compose` reads these from the environment; nothing in
the repository holds a production secret.

Rotating `JWT_SECRET` invalidates every access and refresh token, signing all
users out. Rotating `PASSWORD_PEPPER` invalidates **every stored password hash**
— nobody can sign in and the only route back is a password reset for every
account. Do not change it on a system with real users.

### Recovering an account

- **Locked out** (5 failed attempts, 15-minute window): wait, or clear
  `locked_until` on the user row.
- **Lost authenticator with recovery codes**: any unused code works in place of
  a TOTP code at sign-in.
- **Lost authenticator, codes gone**: an admin clears the enrolment —
  `POST /api/v1/users/{id}/mfa/reset`.
- **Lost the only super admin**: no API path by design; an admin cannot modify
  a super admin. Set `is_super_admin` directly on the row.
