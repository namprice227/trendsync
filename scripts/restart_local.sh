#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-$ROOT_DIR/.conda/trendsync-py312/bin/python}"
REDIS_BIN="${REDIS_BIN:-$ROOT_DIR/.conda/trendsync-py312/bin/redis-server}"
API_HOST="${API_HOST:-0.0.0.0}"
API_PORT="${API_PORT:-8011}"
WEB_PORT="${WEB_PORT:-8081}"
REDIS_PORT="${REDIS_PORT:-6379}"
LEGACY_API_PORT="${LEGACY_API_PORT:-8010}"
RUN_DIR="$ROOT_DIR/logs/local-run"

mkdir -p "$RUN_DIR"

if [[ ! -x "$PYTHON_BIN" ]]; then
  echo "Missing Python environment at $PYTHON_BIN"
  echo "Create it with: conda env create -p \"$ROOT_DIR/.conda/trendsync-py312\" -f environment.yml && \"$ROOT_DIR/.conda/trendsync-py312/bin/python\" -m pip install -r requirements.txt"
  exit 1
fi

if [[ ! -x "$REDIS_BIN" ]]; then
  REDIS_BIN="$(command -v redis-server || true)"
fi
if [[ -z "$REDIS_BIN" ]]; then
  echo "Missing redis-server. Install the conda environment from environment.yml first."
  exit 1
fi

export PYTHONNOUSERSITE="${PYTHONNOUSERSITE:-1}"
export PATH="$(dirname "$PYTHON_BIN"):$PATH"
export TRIPSTORY_REDIS_URL="${TRIPSTORY_REDIS_URL:-redis://127.0.0.1:${REDIS_PORT}/0}"
if [[ -n "${EXPO_PUBLIC_API_URL:-}" ]]; then
  export EXPO_PUBLIC_API_URL
else
  unset EXPO_PUBLIC_API_URL
fi
export EXPO_PUBLIC_API_PORT="${EXPO_PUBLIC_API_PORT:-$API_PORT}"

stop_pid_file() {
  local name="$1"
  local pid_file="$RUN_DIR/${name}.pid"
  if [[ -f "$pid_file" ]]; then
    local pid
    pid="$(cat "$pid_file" 2>/dev/null || true)"
    if [[ "$pid" =~ ^[0-9]+$ ]] && kill -0 "$pid" 2>/dev/null; then
      echo "Stopping $name pid $pid"
      kill "$pid" 2>/dev/null || true
    fi
    rm -f "$pid_file"
  fi
}

stop_port() {
  local port="$1"
  if command -v lsof >/dev/null 2>&1; then
    local pids
    pids="$(lsof -ti tcp:"$port" 2>/dev/null || true)"
    if [[ -n "$pids" ]]; then
      echo "Stopping processes on port $port: $pids"
      kill $pids 2>/dev/null || true
    fi
  elif command -v fuser >/dev/null 2>&1; then
    echo "Stopping processes on port $port"
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
}

stop_patterns() {
  pkill -f "python worker.py" 2>/dev/null || true
  pkill -f "uvicorn api_server:app" 2>/dev/null || true
  pkill -f "expo start --web" 2>/dev/null || true
}

wait_for_stop() {
  sleep 1
}

port_open() {
  local port="$1"
  "$PYTHON_BIN" - "$port" <<'PY'
import socket
import sys

port = int(sys.argv[1])
with socket.socket() as sock:
    sock.settimeout(0.25)
    raise SystemExit(0 if sock.connect_ex(("127.0.0.1", port)) == 0 else 1)
PY
}

start_service() {
  local name="$1"
  shift
  local log_file="$RUN_DIR/${name}.log"
  echo "Starting $name"
  nohup "$@" >"$log_file" 2>&1 &
  echo "$!" >"$RUN_DIR/${name}.pid"
}

health_check() {
  local url="$1"
  local name="$2"
  for _ in {1..80}; do
    if curl -fsS "$url" >/dev/null 2>&1; then
      echo "$name is ready: $url"
      return 0
    fi
    sleep 0.5
  done
  echo "$name did not respond yet. Check logs in $RUN_DIR"
  return 1
}

for name in redis worker api web; do
  stop_pid_file "$name"
done
stop_port "$API_PORT"
if [[ "$API_PORT" != "$LEGACY_API_PORT" ]]; then
  stop_port "$LEGACY_API_PORT"
fi
stop_port "$WEB_PORT"
stop_patterns
wait_for_stop

if port_open "$API_PORT"; then
  echo "API port $API_PORT is still occupied after stop. Try API_PORT=<free-port> scripts/restart_local.sh" >&2
  exit 1
fi

if port_open "$REDIS_PORT"; then
  echo "Redis already listening on 127.0.0.1:$REDIS_PORT; reusing it"
  rm -f "$RUN_DIR/redis.pid"
else
  start_service redis "$REDIS_BIN" --port "$REDIS_PORT" --save "" --appendonly no
fi
start_service worker "$PYTHON_BIN" worker.py
start_service api "$PYTHON_BIN" -m uvicorn api_server:app --host "$API_HOST" --port "$API_PORT"

if [[ ! -d "$ROOT_DIR/mobile/node_modules" ]]; then
  echo "Installing mobile dependencies"
  (cd "$ROOT_DIR/mobile" && npm ci)
fi
start_service web npm --prefix "$ROOT_DIR/mobile" run web -- --clear --port "$WEB_PORT"

health_check "http://127.0.0.1:${API_PORT}/health" "API"
health_check "http://127.0.0.1:${WEB_PORT}" "Web"

echo
echo "TripStory is running."
echo "API: http://127.0.0.1:${API_PORT}"
echo "Web: http://127.0.0.1:${WEB_PORT}"
echo "Logs: $RUN_DIR"
echo "Stop: scripts/stop_local.sh or rerun scripts/restart_local.sh"
