# TripStory Production Hardening

This no-spend production setup keeps development and production separate on the
same server. Development can stay in `/home/ubuntu/trendsync`; production runs
from `/opt/tripstory/app`, stores state under `/var/lib/tripstory`, reads
secrets from `/etc/tripstory/tripstory.env`, and is managed by systemd units
named `tripstory-*`.

The production web app is a static Cloudflare Pages deployment for
`mangasmith.com` and `www.mangasmith.com`. The API is exposed at
`api.mangasmith.com` through Cloudflare Tunnel to local `127.0.0.1:8010`.
Do not expose the Expo dev server on port `8081` as production.

## Production Host Bootstrap

From a checked-out repo on the server:

```bash
sudo scripts/bootstrap_production_host.sh
sudoedit /etc/tripstory/tripstory.env
STOP_LEGACY_USER_SERVICES=1 scripts/deploy_production.sh --local
```

The bootstrap script installs these system services:

- `tripstory-api.service`
- `tripstory-worker.service`
- `tripstory-redis.service`
- `tripstory-tunnel.service`

The deploy script creates or updates `/opt/tripstory/app`, creates the Conda
environment at `/opt/tripstory/env`, runs backend tests and mobile typecheck,
exports the frontend to `/opt/tripstory/frontend-dist`, and restarts the
production services.

Use `--local` for the first cutover while these production scripts are still
only in the current working tree. After the changes are pushed, use a branch or
commit, for example `scripts/deploy_production.sh main`.

Set `PUBLISH_FRONTEND=1` only after the Cloudflare Pages project is configured:

```bash
PUBLISH_FRONTEND=1 scripts/deploy_production.sh main
```

## Required Cloudflare Access setup

1. In Cloudflare Zero Trust, create a self-hosted Access application for:
   - `mangasmith.com`
   - `www.mangasmith.com`
   - `api.mangasmith.com`
2. Add one allow policy with only the approved email addresses.
3. Keep share links private. Do not add a bypass policy for `/share/*` or
   `/files/*`.
4. Add Cloudflare rate limits/WAF rules for expensive API paths:
   - `POST /sessions`
   - `POST /sessions/*/media`
   - `POST /sessions/*/generate-story`
   - `POST /sessions/*/render`
   - `POST /sessions/*/duplicate`
   - `DELETE /sessions/*`

## Backend production flags

After the Access application and allow policy are active, `/etc/tripstory/tripstory.env`
must include:

```bash
TRIPSTORY_REQUIRE_CLOUDFLARE_ACCESS=1
TRIPSTORY_TRUST_CLOUDFLARE_ACCESS_EMAIL=1
TRIPSTORY_CORS_ORIGINS=https://mangasmith.com,https://www.mangasmith.com
```

With these flags, session routes reject requests that do not include
Cloudflare Access identity, and the Access email becomes the project owner id.
Client-supplied owner headers cannot override it.

## Service Operations

```bash
systemctl status tripstory-api tripstory-worker tripstory-tunnel tripstory-redis
systemctl restart tripstory-api tripstory-worker tripstory-tunnel tripstory-redis
journalctl -u tripstory-api -f
journalctl -u tripstory-worker -f
tail -f /var/log/tripstory/app.log
scripts/check_production.sh
```

Only one production API and one production worker should be running. If a manual
dev process binds port `8010`, the production API will fail with `address
already in use`.

## Verification

Unauthenticated requests should be blocked by Cloudflare Access:

```bash
curl -I https://mangasmith.com
curl -I https://api.mangasmith.com/health
```

After logging in with an allowed email, the dashboard should load and project
actions should work. Public media URLs under `/files/` must also require the
same Access login.
