#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PYTHON="$ROOT_DIR/.conda/trendsync-py312/bin/python"

if [[ -x "${TRENDSYNC_PYTHON:-}" ]]; then
  PYTHON="$TRENDSYNC_PYTHON"
elif [[ -x "$DEFAULT_PYTHON" ]]; then
  PYTHON="$DEFAULT_PYTHON"
elif command -v python3 >/dev/null 2>&1; then
  PYTHON="$(command -v python3)"
else
  echo "ERROR: Python was not found. Run ./setup.sh first or set TRENDSYNC_PYTHON." >&2
  exit 1
fi

DUMMY_HOST="${TRENDFLOW_DUMMY_HOST:-127.0.0.1}"
APP_HOST="${TRENDFLOW_APP_HOST:-127.0.0.1}"
APP_PORT="${TRENDFLOW_APP_PORT:-7860}"
ANALYSIS_PORT="${TRENDFLOW_DUMMY_ANALYSIS_PORT:-8000}"
DIRECTOR_PORT="${TRENDFLOW_DUMMY_DIRECTOR_PORT:-8001}"

export MPLCONFIGDIR="${MPLCONFIGDIR:-/tmp/mpl}"
export TRENDFLOW_ANALYSIS_MODEL="${TRENDFLOW_ANALYSIS_MODEL:-Qwen/Qwen3.6-35B-A3B}"
export TRENDFLOW_DIRECTOR_MODEL="${TRENDFLOW_DIRECTOR_MODEL:-mistralai/Pixtral-12B-2409}"
export TRENDFLOW_VLLM_URL="http://${DUMMY_HOST}:${ANALYSIS_PORT}/v1/chat/completions"
export TRENDFLOW_DIRECTOR_VLLM_URL="http://${DUMMY_HOST}:${DIRECTOR_PORT}/v1/chat/completions"

mkdir -p "$MPLCONFIGDIR"

cleanup() {
  if [[ -n "${ANALYSIS_PID:-}" ]]; then
    kill "$ANALYSIS_PID" >/dev/null 2>&1 || true
  fi
  if [[ -n "${DIRECTOR_PID:-}" ]]; then
    kill "$DIRECTOR_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

echo "[dummy-ui] Python: $PYTHON"
echo "[dummy-ui] Analysis endpoint: $TRENDFLOW_VLLM_URL"
"$PYTHON" "$ROOT_DIR/dummy_vllm_server.py" \
  --host "$DUMMY_HOST" \
  --port "$ANALYSIS_PORT" \
  --model "$TRENDFLOW_ANALYSIS_MODEL" &
ANALYSIS_PID=$!

echo "[dummy-ui] Director endpoint: $TRENDFLOW_DIRECTOR_VLLM_URL"
"$PYTHON" "$ROOT_DIR/dummy_vllm_server.py" \
  --host "$DUMMY_HOST" \
  --port "$DIRECTOR_PORT" \
  --model "$TRENDFLOW_DIRECTOR_MODEL" &
DIRECTOR_PID=$!

sleep 1

echo "[dummy-ui] Starting TrendFlow UI on http://${APP_HOST}:${APP_PORT}"
"$PYTHON" -c "import app; app.launch_demo(server_name='$APP_HOST', server_port=$APP_PORT, share=False)"
