#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MODE="${1:-auto}"
PROD_ENV_FILE="${PROD_ENV_FILE:-/etc/tripstory/tripstory.env}"
SERVICE_PREFIX="${SERVICE_PREFIX:-tripstory}"
PUBLIC_API_URL="${PUBLIC_API_URL:-https://api.mangasmith.com}"
PUBLIC_WEB_URL="${PUBLIC_WEB_URL:-https://mangasmith.com}"
CLOUDFLARE_PAGES_PROJECT="${CLOUDFLARE_PAGES_PROJECT:-trendsync}"
CLOUDFLARE_PAGES_BRANCH="${CLOUDFLARE_PAGES_BRANCH:-main}"

usage() {
  cat <<'EOF'
Usage: scripts/deploy_mangasmith.sh [auto|frontend|production]

auto        Full deploy on the production host; frontend-only deploy elsewhere.
frontend    Build and publish only the Cloudflare Pages frontend.
production  Run the full backend + frontend production deploy from local source.

Optional env:
  PUBLIC_API_URL=https://api.mangasmith.com
  PUBLIC_WEB_URL=https://mangasmith.com
  CLOUDFLARE_PAGES_PROJECT=trendsync
  CLOUDFLARE_PAGES_BRANCH=main
EOF
}

if [[ "$MODE" == "-h" || "$MODE" == "--help" ]]; then
  usage
  exit 0
fi

if [[ "$MODE" != "auto" && "$MODE" != "frontend" && "$MODE" != "production" ]]; then
  usage >&2
  exit 2
fi

load_local_env() {
  local env_file="${ENV_FILE:-$ROOT_DIR/.env}"
  if [[ -f "$env_file" ]]; then
    set -a
    # shellcheck disable=SC1090
    . "$env_file"
    set +a
  fi
  export CLOUDFLARE_API_TOKEN="${CLOUDFLARE_API_TOKEN:-${CLOUDFARE_API_TOKEN:-}}"
  export CLOUDFLARE_ACCOUNT_ID="${CLOUDFLARE_ACCOUNT_ID:-02749e6cf37c731b9ee991419cf4fdc6}"
}

prepare_node_tools() {
  export NPM_CONFIG_CACHE="${NPM_CONFIG_CACHE:-${npm_config_cache:-/tmp/tripstory-npm-cache}}"
  export npm_config_cache="$NPM_CONFIG_CACHE"
  export XDG_CONFIG_HOME="${XDG_CONFIG_HOME:-/tmp/tripstory-xdg}"
  mkdir -p "$NPM_CONFIG_CACHE" "$XDG_CONFIG_HOME"
}

has_production_services() {
  [[ -f "$PROD_ENV_FILE" ]] || return 1
  command -v systemctl >/dev/null 2>&1 || return 1
  systemctl cat "${SERVICE_PREFIX}-api.service" >/dev/null 2>&1
}

deploy_frontend() {
  load_local_env
  prepare_node_tools

  if [[ -z "${CLOUDFLARE_API_TOKEN:-}" ]]; then
    echo "Missing CLOUDFLARE_API_TOKEN. Add it to .env or export it, then rerun." >&2
    exit 1
  fi

  (
    cd "$ROOT_DIR/mobile"
    npm ci
    npm run typecheck
    EXPO_PUBLIC_API_URL="$PUBLIC_API_URL" npx expo export -p web --output-dir dist
    npx wrangler pages deploy dist --project-name "$CLOUDFLARE_PAGES_PROJECT" --branch "$CLOUDFLARE_PAGES_BRANCH" --commit-dirty=true
  )

  curl -fsSI --max-time 20 "$PUBLIC_WEB_URL" >/dev/null
  curl -fsS --max-time 20 "$PUBLIC_API_URL/health" >/dev/null
  echo "Mangasmith frontend deployed and public checks passed."
}

deploy_production() {
  prepare_node_tools
  PUBLISH_FRONTEND=1 LOCAL_SOURCE_DIR="$ROOT_DIR" "$ROOT_DIR/scripts/deploy_production.sh" --local
}

case "$MODE" in
  frontend)
    deploy_frontend
    ;;
  production)
    deploy_production
    ;;
  auto)
    if has_production_services; then
      deploy_production
    else
      echo "Production services were not found on this machine; deploying frontend only."
      deploy_frontend
    fi
    ;;
esac
