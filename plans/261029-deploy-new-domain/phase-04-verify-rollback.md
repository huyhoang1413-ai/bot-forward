# Phase 04 — Verify + rollback

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-03

## Overview
- Date: 2026-10-29
- Description: Confirm the new domain serves the panel and (B/C) bots receive webhooks there; keep a clean rollback.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `/healthz` proves nginx→app path. `getWebhookInfo` proves Telegram delivery host (B/C).

## Requirements
- Panel reachable + login works on the new domain; bots still forwarding.

## Verify
```bash
curl -s https://<newdomain>/healthz && echo          # {"ok":true}
# browser: https://<newdomain> -> login works, 🔒 valid cert
# B/C: per bot token, check the webhook host:
curl -s "https://api.telegram.org/bot<TOKEN>/getWebhookInfo"   # url -> https://<newdomain>/webhook/<id>
# send a test message in a source group -> arrives at dest
```

## Rollback
- **A**: remove the new vhost + reload nginx (no app impact).
  `rm /etc/nginx/sites-enabled/<newdomain> && nginx -t && systemctl reload nginx`
- **B**: revert `PUBLIC_URL` to the old domain in `.env`, `docker compose up -d` (resync re-points
  webhooks back). Old vhost/cert still present → instant.
- **C**: `cd ~/bot-forward-2/webapp && docker compose down`; remove its vhost. Instance 1 untouched.

## Related code files
- VPS config only.

## Implementation Steps
1. healthz + browser login. 2. (B/C) getWebhookInfo + live message test. 3. If broken → rollback above.

## Todo list
- [ ] healthz OK on new domain
- [ ] login OK (valid cert)
- [ ] (B/C) getWebhookInfo shows new domain + a test message forwards
- [ ] rollback steps confirmed available

## Success Criteria
- New domain fully serves the panel; forwarding unaffected; rollback is one revert away.

## Risk Assessment
- Low once verified. Biggest risk is B with a wrong PUBLIC_URL → bots silent; rollback is immediate.

## Security Considerations
- Ensure HTTPS redirect active; no plaintext login. Secrets unchanged (A/B) or fresh (C).

## Next steps
Done. Optionally retire the old domain (B) after a stable period.
