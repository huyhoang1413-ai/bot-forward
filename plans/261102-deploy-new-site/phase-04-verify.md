# Phase 04 — Verify + add bots

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-03

## Overview
- Date: 2026-11-02
- Description: Confirm the new site serves the panel over HTTPS, then add bots (they webhook to the new domain).
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- `/healthz` proves nginx/caddy→app path. Each bot added via the panel runs setWebhook to PUBLIC_URL.

## Requirements
- Panel reachable + login works on `<newdomain>`; bots forward.

## Verify
```bash
curl -s https://<newdomain>/healthz && echo          # {"ok":true}
docker compose ps                                     # containers Up
```
Browser: `https://<newdomain>` → 🔒 valid cert → login with the new admin → paste a bot token
(setWebhook → `https://<newdomain>/webhook/<id>`), `/setprivacy` Disable, add routes, test a message.

## Related code files
- None.

## Implementation Steps
1. healthz + `docker compose ps`. 2. Browser login. 3. Add a bot + a route + send a test message.

## Todo list
- [ ] healthz `{"ok":true}` on `<newdomain>`
- [ ] login works (valid cert)
- [ ] add bot → forwards a test message

## Success Criteria
- New independent site live on `<newdomain>`; its own bots forwarding; no data shared with the old site.

## Risk Assessment
- Low once healthz passes. If setWebhook fails for a bot → DNS/cert not ready; wait + `docker compose restart web`.

## Security Considerations
- HTTPS only. Secrets fresh. Back up `BOT_TOKEN_KEK`.

## Next steps
Done. Maintenance: `cd ~/bot-forward && git pull && cd webapp && docker compose up -d --build`.
