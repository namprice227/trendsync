#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RUN_DIR="$ROOT_DIR/logs/local-run"
API_PORT="${API_PORT:-8011}"
WEB_PORT="${WEB_PORT:-8081}"
LEGACY_API_PORT="${LEGACY_API_PORT:-8010}"

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

for name in redis worker api web; do
  stop_pid_file "$name"
done
stop_port "$API_PORT"
if [[ "$API_PORT" != "$LEGACY_API_PORT" ]]; then
  stop_port "$LEGACY_API_PORT"
fi
stop_port "$WEB_PORT"
pkill -f "python worker.py" 2>/dev/null || true
pkill -f "uvicorn api_server:app" 2>/dev/null || true
pkill -f "expo start --web" 2>/dev/null || true

echo "TripStory local services stopped."
