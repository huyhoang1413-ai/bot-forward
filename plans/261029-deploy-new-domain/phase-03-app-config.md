# Phase 03 — App config (scenario branch)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-02

## Overview
- Date: 2026-10-29
- Description: Apply the per-scenario app change. A = none; B = move PUBLIC_URL + resync webhooks; C = stand up a second isolated instance.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `PUBLIC_URL` is the host Telegram posts webhooks to. Only change it when you want bots to RECEIVE
  on the new domain (B/C). Startup `resync_all_webhooks` re-runs setWebhook for active bots.

## Scenario A — Alias (no app change)
- Nothing. Panel is now reachable at `https://<newdomain>` too; bots still webhook to the old domain.
- Caveat: logging in via the new domain works; webhooks keep using `bots.wefunmedia.com`.

## Scenario B — Move (bots' webhooks follow the new domain)
```bash
cd ~/bot-forward/webapp
sed -i 's#^PUBLIC_URL=.*#PUBLIC_URL=https://<newdomain>#' .env
grep PUBLIC_URL .env
docker compose up -d        # restart; lifespan resync re-points every active bot's webhook
docker compose logs --tail=20   # watch setWebhook 200 OK per bot
```
- Old `bots.wefunmedia.com` vhost may stay (alias) or be removed later. Telegram now delivers to the
  new domain only (one webhook URL per bot).

## Scenario C — Second independent instance (same VPS, new port)
```bash
git clone https://github.com/huyhoang1413-ai/bot-forward.git ~/bot-forward-2
cd ~/bot-forward-2/webapp
cp .env.example .env            # NEW secrets: fresh BOT_TOKEN_KEK, SESSION_SECRET, ADMIN_*
#   set PUBLIC_URL=https://<newdomain>, ENVIRONMENT=prod
cat > docker-compose.override.yml <<'EOF'
services:
  web:
    container_name: bot-forward-web-2
    ports: ["127.0.0.1:8001:8000"]
  caddy:
    profiles: ["disabled"]
EOF
docker compose up -d --build
# phase-02 vhost for <newdomain> must proxy_pass 127.0.0.1:8001
```
- Fully separate DB (own volume), bots, admin, KEK. No data shared with instance 1.

## Related code files
- B: `~/bot-forward/webapp/.env`.
- C: `~/bot-forward-2/webapp/.env` + `docker-compose.override.yml`.

## Implementation Steps
1. Pick scenario. 2. Apply the block above. 3. Restart (B/C). 4. Confirm startup clean.

## Todo list
- [ ] (B) PUBLIC_URL updated + container restarted + webhooks resynced
- [ ] (C) second instance up on :8001 with its own .env/KEK

## Success Criteria
- A: new domain opens panel. B: `getWebhookInfo` shows new-domain URL for each bot. C: second panel
  live on new domain, isolated DB.

## Risk Assessment
- B: if PUBLIC_URL wrong or DNS/cert not ready, setWebhook fails → bots stop receiving. Verify phase-02
  first. Keep the old vhost until B is confirmed (easy rollback).
- C: port/volume/container-name must differ from instance 1 to avoid cl/collision.

## Security Considerations
- C: generate a NEW `BOT_TOKEN_KEK` (back it up) — never reuse across instances. Don't copy the live DB.

## Next steps
Phase 04: verify + rollback.
