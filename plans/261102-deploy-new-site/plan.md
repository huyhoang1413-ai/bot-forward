# Plan: Deploy the SAME code to a new website (independent instance)

Date: 2026-11-02 · Status: Ready to run · Priority: High · Type: Ops (no code change)

## Goal
Run the current code (commit `b2a107d`, unchanged) on a NEW domain as a fully independent instance
(own DB/bots/admin/KEK). Repo is PUBLIC now → clone needs no token.

## Path A (recommended) — Fresh VPS + Caddy (auto-TLS)
Simplest for a brand-new box (nothing on 80/443). The repo's base compose already runs Caddy.
1. **phase-01-dns.md** — point `<newdomain>` A-record → `<new VPS IP>`, DNS-only (grey) if Cloudflare.
2. **phase-02-vps-docker.md** — SSH, install Docker, confirm 80/443 free, firewall 80/443.
3. **phase-03-clone-config-run.md** — `git clone` (public, no token); edit `webapp/Caddyfile` →
   `<newdomain>`; create `webapp/.env` (fresh KEK, SESSION, ADMIN_*, `PUBLIC_URL=https://<newdomain>`,
   `ENVIRONMENT=prod`); `docker compose up -d --build` (Caddy issues the cert).
4. **phase-04-verify.md** — `https://<newdomain>/healthz` → `{"ok":true}`, login, add bots.

## Path B — Same VPS as the current site (nginx + port 8001)
Only if you must reuse `103.179.184.26` (it already runs host nginx). Then: clone to a 2nd dir,
`docker-compose.override.yml` publishing `127.0.0.1:8001:8000` + `caddy profiles:["disabled"]`,
a new nginx vhost proxy_pass 8001 + `certbot -d <newdomain>`, own volume/container name.
(See `plans/261029-deploy-new-domain/phase-03-app-config.md` scenario C for exact commands.)

## Required inputs (confirm before running)
- **New domain** + is it on **Cloudflare**? (→ grey-cloud it.)
- **Fresh VPS IP** (Path A) OR "same VPS, port 8001" (Path B).
- New **admin username/password** + a **fresh BOT_TOKEN_KEK** (back it up; never reuse).

## Key facts
- PUBLIC_URL = the host Telegram sends webhooks to (per bot). Bots are added fresh via the panel.
- DB on volume `app_data`; migrations run on startup. No data shared with the current site.
- Teams already isolate clients inside one instance — a 2nd instance is only for a truly separate system.

## Phases
1. [phase-01-dns.md](./phase-01-dns.md)
2. [phase-02-vps-docker.md](./phase-02-vps-docker.md)
3. [phase-03-clone-config-run.md](./phase-03-clone-config-run.md)
4. [phase-04-verify.md](./phase-04-verify.md)

## Open questions / decisions for reviewer
1. **Path A (fresh VPS, Caddy)** or **Path B (same VPS, nginx :8001)**?
2. New domain name + Cloudflare yes/no?
3. Fresh VPS IP (Path A)?
