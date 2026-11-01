# Scout Report 01 — Current deploy (to base a new-domain plan on)

Author: main agent (firsthand — set up the live deploy). Scope: webapp/ + VPS.

## Current live deployment
- **VPS**: Ubuntu 22.04, IP `103.179.184.26`. Runs OTHER sites via host **nginx** (ports 80/443).
- **App**: Docker Compose in `~/bot-forward/webapp`. Only the `web` service runs
  (`docker-compose.override.yml`: `web` published on `127.0.0.1:8000`; `caddy` disabled via
  `profiles:["disabled"]`). SQLite DB on named volume `app_data` at `/app/data/app.db`.
- **Reverse proxy**: host nginx vhost `/etc/nginx/sites-available/bots.wefunmedia.com` →
  `proxy_pass http://127.0.0.1:8000`. TLS via **certbot --nginx** (Let's Encrypt, auto-renew).
- **Domain**: `bots.wefunmedia.com` → A record `103.179.184.26` (Cloudflare **DNS-only/grey**).
- **App config** (`webapp/.env`): `PUBLIC_URL=https://bots.wefunmedia.com` (used to build each
  bot's webhook URL at setWebhook time), `ENVIRONMENT=prod` (Secure cookies), `BOT_TOKEN_KEK`,
  `ADMIN_*`, `SESSION_SECRET`.

## Key facts that constrain "deploy to another domain"
- **PUBLIC_URL is single-valued** and drives `setWebhook` → `https://<PUBLIC_URL>/webhook/{bot_id}`.
  Telegram sends ONE webhook URL per bot. So the domain that RECEIVES webhooks = PUBLIC_URL's host.
  Changing the serving domain for bots ⇒ must update PUBLIC_URL **and re-run setWebhook** for all
  active bots (startup `resync_all_webhooks` does this when the container restarts, if PUBLIC_URL
  changed and `RESYNC_WEBHOOKS_ON_STARTUP` true — default true).
- Multi-tenant is per-**team** inside ONE instance; a second domain is NOT required to separate
  clients (teams already do that). A separate instance = separate DB/bots.
- Webhook path auth = bot_id + secret header; host-agnostic. Cookies Secure in prod (HTTPS ok).
- nginx can serve MANY vhosts on the same IP; certbot issues a cert per domain.

## Three scenarios (the plan's branch point)
- **A. Add an alias domain to the SAME instance** (panel reachable at new domain too; bots keep
  using the old domain for webhooks). Cheapest: new DNS + new nginx vhost (same proxy_pass:8000) +
  certbot. No app/env change. PUBLIC_URL unchanged → webhooks still hit old domain.
- **B. MOVE to a new domain** (new domain becomes the primary; bots' webhooks move to it). New DNS +
  vhost + cert, THEN set `PUBLIC_URL=https://newdomain`, restart container → resync re-points every
  bot's webhook to the new domain. Optionally keep old vhost as alias or remove.
- **C. SECOND independent instance** (new domain, separate bots/DB, same VPS). New compose project
  dir + its own `.env` (fresh KEK, `PUBLIC_URL=https://newdomain`) on a DIFFERENT local port
  (e.g. 127.0.0.1:8001) + its own nginx vhost + cert + volume. Fully isolated.

## Files involved
- VPS only (no repo code change): `/etc/nginx/sites-available/<newdomain>`, certbot,
  `webapp/.env` (PUBLIC_URL for B), and for C a second checkout + override with a new port.
- Repo `webapp/Caddyfile` is unused (nginx path chosen); ignore.

## Open questions for the plan
- Which scenario (A alias / B move / C separate instance)?
- Is the new domain on Cloudflare too? (→ set DNS-only/grey so certbot HTTP-01 works, like before.)
- For C: same VPS (new port) or a new VPS?
