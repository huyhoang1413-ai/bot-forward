# Scout Report 01 — Deploy the SAME code to a new website (fresh instance)

Author: main agent (firsthand — set up the live deploy + repo). Scope: VPS + repo.

## Goal
Deploy the current code (unchanged) to a NEW domain as an independent instance — own DB, bots,
admin, KEK. No code change.

## What a fresh clone gets now
- Repo `https://github.com/huyhoang1413-ai/bot-forward.git` is **PUBLIC** → `git clone` needs NO
  auth/token. Latest commit `b2a107d` includes ALL features (multi-tenant, topics, auto-nick,
  reply-aware, etc.).
- Base `docker-compose.yml` runs BOTH `web` (expose 8000) + `caddy` (binds 80/443, auto-TLS via
  Let's Encrypt from `Caddyfile`). There is NO `docker-compose.override.yml` in the repo → a fresh
  clone uses Caddy by default (the simplest path for a brand-new box).
- `docker-compose.yml` sets `DATABASE_URL=sqlite:////app/data/app.db` + `ENVIRONMENT=prod`; DB
  persists on the `app_data` volume. Migrations run on startup (additive). `.env` is gitignored.

## Two realistic targets
- **Fresh VPS (recommended for a new site)**: nothing on 80/443 → use the repo's Caddy (auto-TLS).
  Just edit the `Caddyfile` domain + create `.env`.
- **Same VPS as bots.wefunmedia.com (103.179.184.26)**: that box already runs host nginx on 80/443
  (Caddy disabled there). A second instance must run on a DIFFERENT local port (e.g. 8001) behind a
  NEW nginx vhost + certbot, with its own compose project/dir/volume/container name. More steps.

## Required inputs (fill before running)
- New domain (e.g. `bot.marioagency.shop`), and whether it's on **Cloudflare** (→ set DNS-only/grey
  so Caddy/certbot TLS works).
- New VPS IP (fresh box recommended) OR confirm "same VPS, new port" (nginx path).
- New admin creds + a FRESH `BOT_TOKEN_KEK` (never reuse across instances; back it up).

## Constraints / facts
- `PUBLIC_URL` is the host Telegram posts webhooks to → set it to the new domain so this instance's
  bots webhook to the new site.
- Webhook auth = bot_id + secret (host-agnostic). Cookies Secure in prod (HTTPS). Teams already
  isolate clients inside ONE instance — a 2nd instance is only for a fully separate system.
- Reuses the exact runbook in `plans/261029-deploy-new-domain/` (fresh VPS + Caddy).

## Open questions
- Fresh VPS (Caddy) or same VPS (nginx, port 8001)?
- New domain + Cloudflare status?
