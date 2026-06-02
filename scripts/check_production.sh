#!/usr/bin/env bash
set -u

SERVICE_PREFIX="${SERVICE_PREFIX:-tripstory}"
LOCAL_API_URL="${LOCAL_API_URL:-http://127.0.0.1:8010}"
PUBLIC_API_URL="${PUBLIC_API_URL:-https://api.mangasmith.com}"
PUBLIC_WEB_URL="${PUBLIC_WEB_URL:-https://mangasmith.com}"
EXPECTED_APP_DIR="${EXPECTED_APP_DIR:-/opt/tripstory/app}"
failures=0

fail() {
  echo "FAIL: $*" >&2
  failures=$((failures + 1))
}

pass() {
  echo "OK: $*"
}

check_service() {
  local service="$1"
  if systemctl is-active --quiet "$service"; then
    pass "$service is active"
  else
    fail "$service is not active"
  fi
}

check_http() {
  local label="$1"
  local url="$2"
  local expected="$3"
  local body
  body="$(curl -fsS --max-time 10 "$url" 2>/dev/null || true)"
  if [[ "$body" == *"$expected"* ]]; then
    pass "$label responds"
  else
    fail "$label did not return expected content from $url"
  fi
}

check_service "$SERVICE_PREFIX-api.service"
check_service "$SERVICE_PREFIX-worker.service"
check_service "$SERVICE_PREFIX-redis.service"
check_service "$SERVICE_PREFIX-tunnel.service"

check_http "local API health" "$LOCAL_API_URL/health" '"status":"ok"'
check_http "public API health" "$PUBLIC_API_URL/health" '"status":"ok"'

web_head="$(curl -fsSI --max-time 10 "$PUBLIC_WEB_URL" 2>/dev/null || true)"
if [[ "$web_head" == *"200"* ]]; then
  pass "public frontend responds"
else
  fail "public frontend did not respond with HTTP 200"
fi

api_processes="$(pgrep -af "uvicorn api_server:app" || true)"
worker_processes="$(pgrep -af "python .*worker.py|python worker.py" || true)"

api_count="$(printf '%s\n' "$api_processes" | sed '/^$/d' | wc -l)"
worker_count="$(printf '%s\n' "$worker_processes" | sed '/^$/d' | wc -l)"

if [[ "$api_count" -eq 1 && "$api_processes" == *"$EXPECTED_APP_DIR"* ]]; then
  pass "exactly one production API process is running"
else
  fail "expected one API process from $EXPECTED_APP_DIR, found $api_count: $api_processes"
fi

if [[ "$worker_count" -eq 1 && "$worker_processes" == *"$EXPECTED_APP_DIR"* ]]; then
  pass "exactly one production worker process is running"
else
  fail "expected one worker process from $EXPECTED_APP_DIR, found $worker_count: $worker_processes"
fi

if [[ "$failures" -gt 0 ]]; then
  echo "$failures production check(s) failed." >&2
  exit 1
fi

echo "Production checks passed."
