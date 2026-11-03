# Phase 03 — Clone + config + run (Caddy)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02

## Overview
- Date: 2026-11-02
- Description: Clone the public repo, point the Caddyfile at the new domain, create a fresh `.env`, and bring it up with Caddy auto-TLS.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Repo is PUBLIC → `git clone` needs no token. Base compose runs Caddy (no override committed).
- Fresh instance = NEW secrets. Never reuse `BOT_TOKEN_KEK` across instances.

## Requirements
- App up on `<newdomain>` with a valid Let's Encrypt cert; own DB/admin.

## Architecture
```bash
git clone https://github.com/huyhoang1413-ai/bot-forward.git ~/bot-forward
cd ~/bot-forward/webapp

# point Caddy at the new domain
sed -i 's/bots\.wefunmedia\.com/<newdomain>/' Caddyfile
cat Caddyfile      # must show <newdomain>

# fresh secrets
cp .env.example .env
echo "KEK     = $(docker run --rm python:3.11-slim python -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"
echo "SESSION = $(openssl rand -hex 32)"
nano .env   # fill below, then Ctrl+O, Enter, Ctrl+X
```
`.env`:
```ini
ADMIN_USERNAME=<new admin>
ADMIN_PASSWORD=<strong password>
SESSION_SECRET=<SESSION printed above>
BOT_TOKEN_KEK=<KEK printed above — BACK IT UP>
PUBLIC_URL=https://<newdomain>
ENVIRONMENT=prod
```
```bash
docker compose up -d --build
docker compose logs -f     # wait: web "Application startup complete" + Caddy cert obtained (~30s)
```

## Related code files
- `~/bot-forward/webapp/Caddyfile` (edited on VPS), `~/bot-forward/webapp/.env` (new).

## Implementation Steps
1. Clone. 2. sed Caddyfile domain. 3. Generate secrets + fill `.env`. 4. `docker compose up -d --build`.

## Todo list
- [ ] clone (no token)
- [ ] Caddyfile → `<newdomain>`
- [ ] `.env` with fresh KEK/SESSION/admin + PUBLIC_URL
- [ ] `docker compose up -d --build` + Caddy cert issued

## Success Criteria
- Containers up (`docker compose ps`), Caddy obtained a cert, web startup complete.

## Risk Assessment
- Medium: Caddy TLS fails if DNS not pointed/grey or 80/443 blocked → fix phase-01/02 first.
  Keep KEK backed up (lose it = can't decrypt stored bot tokens).

## Security Considerations
- Fresh `BOT_TOKEN_KEK` + strong admin password. `.env` gitignored. Don't paste secrets into chats/screenshots.

## Next steps
Phase 04: verify + add bots.
