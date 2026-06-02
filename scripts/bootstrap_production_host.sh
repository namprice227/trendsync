#!/usr/bin/env bash
set -euo pipefail

PROD_ROOT="${PROD_ROOT:-/opt/tripstory}"
PROD_APP_DIR="${PROD_APP_DIR:-$PROD_ROOT/app}"
PROD_ENV_DIR="${PROD_ENV_DIR:-/etc/tripstory}"
PROD_ENV_FILE="${PROD_ENV_FILE:-$PROD_ENV_DIR/tripstory.env}"
PROD_DATA_DIR="${PROD_DATA_DIR:-/var/lib/tripstory}"
PROD_LOG_DIR="${PROD_LOG_DIR:-/var/log/tripstory}"
TRIPSTORY_USER="${TRIPSTORY_USER:-${SUDO_USER:-ubuntu}}"
TRIPSTORY_GROUP="${TRIPSTORY_GROUP:-$TRIPSTORY_USER}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "${EUID}" -ne 0 ]]; then
  echo "Run with sudo: sudo $0" >&2
  exit 1
fi

if ! id "$TRIPSTORY_USER" >/dev/null 2>&1; then
  echo "Service user '$TRIPSTORY_USER' does not exist." >&2
  exit 1
fi

install -d -o "$TRIPSTORY_USER" -g "$TRIPSTORY_GROUP" "$PROD_ROOT" "$PROD_APP_DIR" "$PROD_DATA_DIR" "$PROD_DATA_DIR/media" "$PROD_LOG_DIR"
install -d -o root -g "$TRIPSTORY_GROUP" -m 0750 "$PROD_ENV_DIR"

if [[ ! -f "$PROD_ENV_FILE" ]]; then
  install -o root -g "$TRIPSTORY_GROUP" -m 0640 "$REPO_ROOT/deployment/tripstory.env.production.example" "$PROD_ENV_FILE"
  echo "Created $PROD_ENV_FILE. Fill in provider and Cloudflare secrets before starting production."
else
  chmod 0640 "$PROD_ENV_FILE"
  chown root:"$TRIPSTORY_GROUP" "$PROD_ENV_FILE"
fi

render_unit() {
  local input="$1"
  local output="$2"
  sed \
    -e "s#@PROD_ROOT@#$PROD_ROOT#g" \
    -e "s#@TRIPSTORY_USER@#$TRIPSTORY_USER#g" \
    -e "s#@TRIPSTORY_GROUP@#$TRIPSTORY_GROUP#g" \
    "$input" > "$output"
  chmod 0644 "$output"
}

for template in "$REPO_ROOT"/deployment/systemd/*.service.in; do
  unit_name="$(basename "${template%.in}")"
  render_unit "$template" "/etc/systemd/system/$unit_name"
done

systemctl daemon-reload
systemctl enable tripstory-api.service tripstory-worker.service tripstory-redis.service tripstory-tunnel.service

echo "Production host bootstrap complete."
echo "Next: edit $PROD_ENV_FILE, then run scripts/deploy_production.sh."
