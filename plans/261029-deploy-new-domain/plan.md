# Plan: Fresh deploy on a NEW VPS + NEW domain (Caddy auto-TLS)

Date: 2026-10-29 · Status: Ready to run · Priority: High · Type: Ops (no code change)

## Target (locked by user)
- **New VPS**: `103.179.184.191` (assumed fresh — nothing on ports 80/443).
- **New domain**: `bot.marioagency.shop`.
- Fully **independent instance**: own DB, bots, admin, KEK. No data shared with VPS1.

## Why Caddy (not nginx+certbot like VPS1)
VPS1 already ran other sites on nginx → we disabled Caddy there. The NEW VPS is fresh → use the
repo's **base `docker-compose.yml` (web + caddy)**: Caddy binds 80/443 and auto-provisions
Let's Encrypt. Confirmed: no `docker-compose.override.yml` in the repo → a fresh clone runs Caddy.
Just edit the Caddyfile domain + create `.env`.

## Pre-flight (must be true before running)
- `bot.marioagency.shop` A-record → `103.179.184.191`, **DNS-only (grey)** if on Cloudflare
  (Caddy HTTP/TLS-ALPN challenge fails behind a CF proxy).
- Ports **80 and 443 free** on the new VPS (fresh box → yes). Verify `ss -tlnp | grep -E ':80 |:443 '` empty.

## Runbook (phases)
1. **phase-01-dns.md** — A record `bot.marioagency.shop` → `103.179.184.191` (grey); verify resolve.
2. **phase-02-vps-docker.md** — SSH, install Docker, confirm 80/443 free, firewall allow 80/443.
3. **phase-03-clone-config.md** — clone repo; edit `webapp/Caddyfile` → `bot.marioagency.shop`;
   create `webapp/.env` (fresh `BOT_TOKEN_KEK`, `SESSION_SECRET`, `ADMIN_*`,
   `PUBLIC_URL=https://bot.marioagency.shop`, `ENVIRONMENT=prod`).
4. **phase-04-run-verify.md** — `docker compose up -d --build`; Caddy issues cert; verify
   `https://bot.marioagency.shop/healthz`, login, add a bot.

## Key facts
- `docker-compose.yml` overrides `DATABASE_URL=sqlite:////app/data/app.db` + `ENVIRONMENT=prod`;
  DB persists on volume `app_data`. Webhook auth = bot_id+secret (host-agnostic).
- This instance's bots are added fresh via the panel (paste token → setWebhook to the new domain).

## Open questions for reviewer
1. Is the new VPS **truly fresh** (nothing serving 80/443)? If it already runs other sites →
   switch to the nginx+certbot path (like VPS1) instead of Caddy.
2. Is `marioagency.shop` on **Cloudflare**? (→ grey-cloud the record.)
3. Login creds for the new panel (ADMIN_USERNAME/PASSWORD) — pick fresh ones.
