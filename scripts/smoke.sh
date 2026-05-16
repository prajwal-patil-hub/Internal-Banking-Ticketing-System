#!/usr/bin/env bash
# Post-deploy smoke test. Run against a live backend to confirm the critical
# endpoints respond. Exits non-zero on the first failure so it composes with
# CI/CD gates.
#
# Usage:
#   API=http://localhost:8000 ./scripts/smoke.sh
#   API=https://api.example.com EMAIL=admin@example.com PASSWORD=Admin@1234 ./scripts/smoke.sh

set -euo pipefail

API="${API:-http://localhost:8000}"
EMAIL="${EMAIL:-admin@example.com}"
PASSWORD="${PASSWORD:-Admin@1234}"

say() { printf '\n\033[1;36m== %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31mFAIL: %s\033[0m\n' "$*" >&2; exit 1; }

require_status() {
  local expected="$1" actual="$2" what="$3"
  [[ "$actual" == "$expected" ]] || fail "$what expected $expected got $actual"
}

say "1. Health check"
status=$(curl -s -o /tmp/smoke.out -w "%{http_code}" "$API/api/v1/healthz")
require_status 200 "$status" "GET /healthz"
grep -q '"alive"' /tmp/smoke.out || fail "/healthz body missing alive"

say "2. Login"
status=$(curl -s -o /tmp/smoke.out -w "%{http_code}" \
  -X POST "$API/api/v1/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASSWORD\"}")
require_status 200 "$status" "POST /auth/login"
TOKEN=$(python3 -c 'import json,sys; print(json.load(open("/tmp/smoke.out"))["data"]["tokens"]["access_token"])')
[[ -n "$TOKEN" ]] || fail "no access token"

say "3. List tickets"
status=$(curl -s -o /tmp/smoke.out -w "%{http_code}" \
  "$API/api/v1/tickets?page=1&per_page=5" \
  -H "Authorization: Bearer $TOKEN")
require_status 200 "$status" "GET /tickets"

say "4. Dashboard endpoints"
for path in kpis sla-status category-distribution department-load recent-tickets ai-metrics; do
  status=$(curl -s -o /dev/null -w "%{http_code}" \
    "$API/api/v1/dashboard/$path" -H "Authorization: Bearer $TOKEN")
  require_status 200 "$status" "GET /dashboard/$path"
done

say "5. Rate-limit headers present"
hdr=$(curl -s -D - -o /dev/null \
  "$API/api/v1/tickets?page=1&per_page=5" \
  -H "Authorization: Bearer $TOKEN" | grep -i '^X-RateLimit-Limit' || true)
[[ -n "$hdr" ]] || fail "missing X-RateLimit-Limit header"

printf '\n\033[1;32mAll smoke checks passed.\033[0m\n'
