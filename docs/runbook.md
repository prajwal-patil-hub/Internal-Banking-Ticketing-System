# Runbook — SUCCESS Bank Internal Ticketing

## 0. Day-1 quick start

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env

make up          # bring up postgres + redis + minio + backend + frontend
make migrate     # apply Alembic migrations
make seed        # roles, permissions, demo branches/categories/users
```

URLs:
- Frontend     http://localhost:5173
- Backend docs http://localhost:8000/api/docs
- MinIO        http://localhost:9001
- Metrics      http://localhost:8000/metrics

Demo passwords are printed once on the first `make seed` invocation.

---

## 1. Migrations

```bash
make migrate            # alembic upgrade head
make migrate-down       # rollback the latest revision
```

Creating a new migration after a model change:

```bash
docker compose -f infra/docker-compose.yml exec backend \
  alembic revision --autogenerate -m "describe change"
```

Review the generated file before committing — autogenerate is best-effort.

---

## 2. Production-style stack

```bash
make prod-build
make prod-up           # nginx :80 -> { /api, /metrics, * }
```

The prod compose file demands `${POSTGRES_USER}` / `${POSTGRES_PASSWORD}` /
`${POSTGRES_DB}` / `${MINIO_ROOT_USER}` / `${MINIO_ROOT_PASSWORD}` to exist
(no defaults). Run with an inline `.env` or shell exports.

After bringing the stack up, apply migrations and (optionally) seed inside
the running backend container:

```bash
docker compose -f infra/docker-compose.prod.yml exec backend alembic upgrade head
```

---

## 3. Operational playbook

### 3.1 SLA breach spike

Symptoms:
- `/sla/breaches` shows growing count, or
- Prometheus alert on `sla_breaches_total` rate.

Triage:
1. Open `/sla` to see *which* priorities are breaching.
2. Check `/escalations?open_only=true` — an automatic L1 escalation is
   raised per breach; supervisors should already be paged via in-app +
   email.
3. If breaches concentrate on one team, look at agent capacity in
   `/users` and the agent's open count in their dashboard.
4. Resolve the underlying ticket(s); the breach flag remains on the
   audit row even after resolution — that's intentional.

### 3.2 Login attack

Symptoms:
- `auth.login` audit rows with `success=false` spike from one IP, or
- `http_requests_total{path="/api/v1/auth/login",status="429"}` rate climbs.

Action:
- The Redis fixed-window limiter caps `/auth/login` at 10/min/IP. If the
  attacker rotates IPs, increase visibility:

  ```bash
  # last 100 failed login attempts per IP
  docker compose -f infra/docker-compose.yml exec postgres \
    psql -U success success_bank -c \
    "SELECT ip_address, count(*) FROM login_attempts \
     WHERE success=false AND attempted_at > now() - interval '1 hour' \
     GROUP BY ip_address ORDER BY count DESC LIMIT 20;"
  ```
- Per-account lockout (5 failures → 15-minute lock) handles credential
  stuffing against a known good email; brute force across emails is
  contained by the IP throttle.
- For sustained pressure, drop the offending CIDR at the load balancer.

### 3.3 Audit-log tampering attempt

Audit logs are protected by a `BEFORE UPDATE OR DELETE` trigger. If you
see `ERROR: audit_logs is append-only` in postgres logs, an upstream code
path tried to mutate audit history — investigate the calling service
*and* page security. The trigger is the last line of defense; any
attempted UPDATE or DELETE is a serious incident.

### 3.4 SLA scheduler not ticking

Check:
1. `docker logs success-backend | grep sla_tick` — should appear roughly
   every minute.
2. Redis lock might be stuck (TTL is 50s; a held lock with TTL > 50s is
   wrong):

   ```bash
   docker compose -f infra/docker-compose.yml exec redis redis-cli get success-bank:sla:lock
   docker compose -f infra/docker-compose.yml exec redis redis-cli ttl success-bank:sla:lock
   ```
3. If the lock is stale, `DEL success-bank:sla:lock` and the next tick
   will reclaim it.

---

## 4. Backups (recommended)

- Postgres: nightly `pg_dump` of the `success_bank` database.
- MinIO: lifecycle-replicated bucket to a secondary site or S3.
- Redis: `appendonly yes` is set; for compliance, snapshot the RDB
  hourly.
- `audit_logs` deserves a separate, write-only S3 export (compliance
  long-tail). The append-only trigger ensures the source is trustworthy;
  the export is the last copy.

---

## 5. Scaling

- Backend is stateless; scale horizontally behind nginx. The SLA
  scheduler is safe at any replica count thanks to the Redis lock.
- Postgres vertical scaling first (banks tend to keep one writer);
  read replicas are easy to add via SQLAlchemy if needed.
- Redis as a single instance is fine until ~50K rate-limit decisions/sec.
