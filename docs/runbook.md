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

Images are built and published by CI, not on the deployment host — what runs
in production is the artefact that passed the gates. Pushing to `main` or a
`v*` tag runs `.github/workflows/cd.yml`, which reruns the full CI suite and
then publishes `backend` and `frontend` to GHCR.

First time on a host:

```bash
cp infra/.env.prod.example infra/.env.prod   # fill in every REQUIRED value
```

Every deploy:

```bash
export IMAGE_TAG=sha-<commit>      # the CD run's summary prints this
cd infra
docker compose -f docker-compose.prod.yml --env-file .env.prod pull
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic upgrade head
```

Prefer the `sha-` tag over `latest`. During an incident the first question is
"which build is running?", and `latest` cannot answer it.

Migrations run as a separate step, not on container start: two backend
replicas booting together would otherwise race on the same migration.

**Back up before migrating.** Some migrations drop columns; `0006` drops four.
There is no undo beyond a restore.

### What the production stack does differently

- Only the frontend publishes a port. Postgres, Redis and MinIO are reachable
  on the internal network and nowhere else.
- No source is mounted. The image is the artefact.
- Every secret is a required variable — `${VAR:?}` — so a missing one stops
  the deploy instead of quietly falling back to a development default.
- Nothing terminates TLS. Put a reverse proxy or load balancer in front before
  this is reachable from anywhere untrusted.

### Rolling back

Application only — code back, schema forward:

```bash
IMAGE_TAG=sha-<previous-commit> \
  docker compose -f infra/docker-compose.prod.yml --env-file infra/.env.prod up -d
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

### `CREATE EXTENSION vector` fails during migration

Migration `0009_knowledge_base` enables pgvector. Two things go wrong here:

- **The image does not ship the extension.** Stock `postgres:15` / `postgres:16`
  do not, and the migration fails with *"could not open extension control
  file"*. All three compose files and CI pin `pgvector/pgvector:pg15` / `pg16`.
  If you are running your own Postgres, install `postgresql-16-pgvector` (or
  build pgvector from source) before migrating.
- **The database role cannot create extensions.** `CREATE EXTENSION` needs
  superuser, or `CREATE` on the database plus the extension being
  allow-listed. On managed Postgres (RDS, Cloud SQL, Supabase) the provider
  usually has to enable it first. Ask a superuser to run
  `CREATE EXTENSION IF NOT EXISTS vector;` once, by hand — the migration is
  idempotent and will skip it on the next run.

Downgrading `0009` drops the six `kb_*` tables but deliberately leaves the
extension in place: another schema in the same database may be using it, and
dropping it cascades to their columns.

### Knowledge-base documents stay stuck on "Indexing" or show "Failed"

Ingestion runs inside the upload request, so a stuck document usually means a
dependency is down rather than a slow parse.

- **Failed with a storage error.** MinIO is unreachable. Same cause as the
  attachment 503 below. Nothing is lost; press **Re-index** once storage is
  back.
- **Failed with an embedding error.** Ollama is down or the embedding model is
  not pulled: `ollama pull nomic-embed-text`. The previous version of the
  document keeps serving answers throughout — a failed re-index degrades to
  "the new copy did not take", never to "the document disappeared".
- **Failed: "appears to be a scanned image".** The PDF has no text layer. OCR
  is not enabled; upload a text-based PDF.
- **Failed: "produces N passages, over the limit".** Split the document. The
  ceiling exists because embedding is sequential and holds the single local
  model, which would stall chat and email intake.

A collection showing **"No roles granted — not searchable"** is not an error:
a new collection is readable by nobody until an administrator grants a role on
the Knowledge Base screen. It is flagged because a granted-to-nobody
collection accepts uploads and answers nothing, which otherwise looks like a
retrieval bug.

### The knowledge base answers "No grounded answer"

This is a success path, not a fault. The service refuses rather than guessing
when retrieval comes back thin, when the model's own citations do not resolve
to real passages, or when derived confidence falls below
`KB_MIN_CONFIDENCE`. The panel states which of those happened. Check
`kb_query_logs.abstain_reason` for the distribution; a spike in
`no_valid_citations` means the model is fabricating sources and is worth
investigating, whereas `no_passages` usually means a document is missing.

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
