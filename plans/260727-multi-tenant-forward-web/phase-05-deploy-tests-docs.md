# Phase 05 — Deployment (Docker + Caddy), Tests, Docs

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: Phases 01–04
- Research: [researcher-02](research/researcher-02-saas-architecture.md) (Docker Compose + Caddy), [researcher-01](research/researcher-01-multibot-runtime.md) (TLS, tunnels)
- Docs: Caddy https://caddyserver.com/docs/ ; Docker Compose https://docs.docker.com/compose/ ; ngrok https://ngrok.com/

## Overview
- **Date**: 2026-07-27
- **Description**: Package the app as Docker Compose (web + PostgreSQL + Caddy auto-TLS), add real tests (crypto, forwarding logic, auth guard, webhook secret), and write setup docs incl. how to expose webhooks locally for development.
- **Priority**: Medium (ship + harden)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Telegram webhooks require **public HTTPS**. Caddy gets a Let's Encrypt cert automatically from the domain and reverse-proxies to FastAPI — bypasses Telegram's port restrictions.
- Local dev without a domain: **ngrok/Cloudflare Tunnel** gives a temporary HTTPS URL; set `PUBLIC_URL` to it and re-run resync.
- No-mock tests: crypto round-trip, `RouteTable`/forwarding dispatch decision (source→dests, loop guard), auth guard redirect, webhook secret rejection. Telegram network calls are the only thing not unit-tested (covered by manual tunnel smoke test).
- `resync_all_webhooks` on startup makes container restarts self-healing.

## Requirements
- `Dockerfile` (python:3.11-slim, uvicorn).
- `docker-compose.yml`: `web`, `db` (postgres:15-alpine, volume), `caddy` (80/443, volumes for certs).
- `Caddyfile`: `your.domain { reverse_proxy web:8000 }`.
- `.env.example` documenting all secrets (ADMIN_PASSWORD, SESSION_SECRET, BOT_TOKEN_KEK, DATABASE_URL, PUBLIC_URL, WEBHOOK_SECRET_SALT).
- Tests in `webapp/tests/` (pytest + httpx TestClient).
- `README.md`: generate KEK, set domain, `docker compose up -d`, add first bot, local-dev via ngrok.

## Architecture
```
webapp/
├── Dockerfile
├── docker-compose.yml
├── Caddyfile
├── .env.example
├── README.md
└── tests/
    ├── test_crypto.py       # encrypt/decrypt round-trip
    ├── test_forwarding.py   # route selection + loop guard (pure)
    ├── test_auth.py         # protected route redirects; login works
    └── test_webhook.py      # wrong secret -> 403 (TestClient, no Telegram)
```
Compose: web depends_on db; caddy proxies web; `restart: unless-stopped` on all.

## Related code files
- `webapp/{Dockerfile,docker-compose.yml,Caddyfile,.env.example,README.md}` (new)
- `webapp/tests/*` (new)

## Implementation Steps
1. Refactor forwarding route-selection into a **pure function** (`select_destinations(routes, source_id)`) so it is unit-testable without Telegram.
2. `test_crypto.py`, `test_forwarding.py`, `test_auth.py`, `test_webhook.py`; `pytest` green.
3. `Dockerfile` + `docker-compose.yml` + `Caddyfile`; `docker compose build`.
4. Bring up stack against a staging domain (or ngrok) and run the onboarding smoke test end-to-end.
5. `README.md` full guide incl. KEK generation and local-dev tunnel.

## Todo list
- [ ] extract pure `select_destinations` + unit tests
- [ ] crypto/auth/webhook tests (no mocks/network)
- [ ] Dockerfile + docker-compose (web+db+caddy) + Caddyfile
- [ ] compose builds & boots; healthz green
- [ ] README (KEK, domain, deploy, ngrok dev flow)

## Success Criteria
- `pytest` passes (crypto, forwarding selection, auth guard, webhook secret) with no mocks/network.
- `docker compose up -d` serves the panel over HTTPS on the domain; webhooks deliver.
- Fresh machine can follow README from zero to a working forwarding bot added via the panel.
- Container restart re-registers all webhooks automatically.

## Risk Assessment
- **Medium**: DNS/TLS misconfig → Caddy cert fails. Document A-record + firewall 80/443.
- **Low**: Postgres volume persistence — ensure named volume; document backups.

## Security Considerations
- Secrets only via env / `.env` (git-ignored); KEK backed up securely (loss = unreadable tokens).
- Caddy enforces HTTPS; HSTS optional. Postgres not exposed publicly (internal network only).
- Document token-compromise recovery: revoke via @BotFather, remove+re-add bot in panel.

## Next steps
- v2 backlog: public multi-user SaaS (users table + RLS + registration), analytics/logs dashboard, message queue (Redis) for high-volume rate control, keyword/media filters, edit/album handling, KEK auto-rotation.
