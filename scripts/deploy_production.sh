#!/usr/bin/env bash
set -euo pipefail

REF="${1:-main}"
PROD_ROOT="${PROD_ROOT:-/opt/tripstory}"
PROD_APP_DIR="${PROD_APP_DIR:-$PROD_ROOT/app}"
PROD_ENV_FILE="${PROD_ENV_FILE:-/etc/tripstory/tripstory.env}"
PROD_FRONTEND_DIR="${PROD_FRONTEND_DIR:-$PROD_ROOT/frontend-dist}"
REPO_URL="${REPO_URL:-https://github.com/namprice227/trendsync.git}"
CONDA_EXE="${CONDA_EXE:-$(command -v conda || true)}"
PY_ENV_DIR="${PY_ENV_DIR:-$PROD_ROOT/env}"
PYTHON_BIN="$PY_ENV_DIR/bin/python"
SERVICE_PREFIX="${SERVICE_PREFIX:-tripstory}"
PUBLISH_FRONTEND="${PUBLISH_FRONTEND:-0}"
CLOUDFLARE_PAGES_PROJECT="${CLOUDFLARE_PAGES_PROJECT:-mangasmith}"
LOCAL_SOURCE_DIR="${LOCAL_SOURCE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)}"
STOP_LEGACY_USER_SERVICES="${STOP_LEGACY_USER_SERVICES:-0}"

systemctl_cmd() {
  if [[ "${EUID}" -eq 0 ]]; then
    systemctl "$@"
  else
    sudo systemctl "$@"
  fi
}

require_file() {
  if [[ ! -f "$1" ]]; then
    echo "Missing required file: $1" >&2
    exit 1
  fi
}

require_env_value() {
  local name="$1"
  if ! grep -Eq "^${name}=.+" "$PROD_ENV_FILE"; then
    echo "Missing production env value: $name in $PROD_ENV_FILE" >&2
    exit 1
  fi
}

require_file "$PROD_ENV_FILE"
require_env_value "TRIPSTORY_PUBLIC_API_URL"
require_env_value "TRIPSTORY_CORS_ORIGINS"
require_env_value "TRIPSTORY_REQUIRE_CLOUDFLARE_ACCESS"
require_env_value "TRIPSTORY_TRUST_CLOUDFLARE_ACCESS_EMAIL"
require_env_value "CLOUDFLARE_API_TOKEN"

legacy_active=0
for legacy_service in trendsync-api.service trendsync-worker.service trendsync-tunnel.service trendsync-redis.service; do
  if systemctl --user is-active --quiet "$legacy_service" 2>/dev/null; then
    legacy_active=1
  fi
done

if [[ "$legacy_active" == "1" ]]; then
  if [[ "$STOP_LEGACY_USER_SERVICES" == "1" ]]; then
    systemctl --user stop trendsync-api.service trendsync-worker.service trendsync-tunnel.service trendsync-redis.service || true
  else
    echo "Legacy trendsync user services are still active and will conflict on ports 8010/6379." >&2
    echo "Rerun with STOP_LEGACY_USER_SERVICES=1 for the initial cutover, or stop them manually first." >&2
    exit 1
  fi
fi

if [[ "$REF" == "--local" ]]; then
  if ! command -v rsync >/dev/null 2>&1; then
    echo "rsync is required for --local deploys." >&2
    exit 1
  fi
  install -d "$PROD_APP_DIR"
  rsync -a --delete \
    --exclude '.env' \
    --exclude '.env.*' \
    --exclude '.conda/' \
    --exclude '.pytest_cache/' \
    --exclude '__pycache__/' \
    --exclude 'logs/' \
    --exclude 'mobile/node_modules/' \
    --exclude 'mobile/dist/' \
    --exclude 'trip_sessions/' \
    --exclude 'trip_sessions.sqlite3*' \
    --exclude 'trip_sessions_sessions.json' \
    "$LOCAL_SOURCE_DIR/" "$PROD_APP_DIR/"
elif [[ -d "$PROD_APP_DIR/.git" ]]; then
  git -C "$PROD_APP_DIR" fetch --prune origin
else
  if [[ -e "$PROD_APP_DIR" && -n "$(find "$PROD_APP_DIR" -mindepth 1 -maxdepth 1 -print -quit 2>/dev/null)" ]]; then
    echo "$PROD_APP_DIR exists but is not a git checkout. Use --local or clear it before git deploy." >&2
    exit 1
  fi
  install -d "$(dirname "$PROD_APP_DIR")"
  git clone "$REPO_URL" "$PROD_APP_DIR"
  git -C "$PROD_APP_DIR" fetch --prune origin
fi

if [[ "$REF" != "--local" ]]; then
  git -C "$PROD_APP_DIR" checkout "$REF"
  if git -C "$PROD_APP_DIR" symbolic-ref -q HEAD >/dev/null; then
    git -C "$PROD_APP_DIR" pull --ff-only
  fi
fi

if [[ ! -x "$PYTHON_BIN" ]]; then
  if [[ -z "$CONDA_EXE" ]]; then
    echo "conda is required to create the production env because ffmpeg and redis come from environment.yml." >&2
    exit 1
  fi
  "$CONDA_EXE" env create -p "$PY_ENV_DIR" -f "$PROD_APP_DIR/environment.yml"
fi

"$PYTHON_BIN" -m pip install -r "$PROD_APP_DIR/requirements.txt"

(
  cd /tmp
  PYTHONPATH="$PROD_APP_DIR" "$PYTHON_BIN" -m unittest tests.test_tripstory_api
)

(
  cd "$PROD_APP_DIR/mobile"
  npm ci
  npm run typecheck
  EXPO_PUBLIC_API_URL=https://api.mangasmith.com npx expo export -p web --output-dir dist
)

rm -rf "$PROD_FRONTEND_DIR"
install -d "$PROD_FRONTEND_DIR"
cp -a "$PROD_APP_DIR/mobile/dist/." "$PROD_FRONTEND_DIR/"

if [[ "$PUBLISH_FRONTEND" == "1" ]]; then
  (
    cd "$PROD_APP_DIR/mobile"
    npx wrangler pages deploy dist --project-name "$CLOUDFLARE_PAGES_PROJECT"
  )
else
  echo "Frontend build ready at $PROD_FRONTEND_DIR."
  echo "Publish it with Cloudflare Pages, or rerun with PUBLISH_FRONTEND=1 after Pages is configured."
fi

systemctl_cmd daemon-reload
systemctl_cmd restart "$SERVICE_PREFIX-redis.service"
systemctl_cmd restart "$SERVICE_PREFIX-api.service"
systemctl_cmd restart "$SERVICE_PREFIX-worker.service"
systemctl_cmd restart "$SERVICE_PREFIX-tunnel.service"

"$PROD_APP_DIR/scripts/check_production.sh"
