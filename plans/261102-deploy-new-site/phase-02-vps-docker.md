# Phase 02 — VPS + Docker

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (DNS resolves)

## Overview
- Date: 2026-11-02
- Description: Prepare the fresh VPS: install Docker, confirm ports 80/443 free (needed by Caddy), open firewall.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Caddy (base compose) binds 80/443 directly → those ports MUST be free. A fresh box = yes.
  If something already listens on 80/443, switch to Path B (nginx :8001) instead.

## Requirements
- Docker + Compose installed; 80/443 free; firewall allows 80/443.

## Architecture / Steps
```bash
ssh root@<VPS_IP>
curl -fsSL https://get.docker.com | sh
docker --version && docker compose version
ss -tlnp | grep -E ':80 |:443 ' || echo "80/443 FREE"   # must be empty
ufw allow 80 && ufw allow 443 2>/dev/null || true
```

## Related code files
- None.

## Implementation Steps
1. Install Docker. 2. Verify versions. 3. Confirm 80/443 free. 4. Allow firewall.

## Todo list
- [ ] Docker + Compose installed
- [ ] 80/443 confirmed free
- [ ] firewall allows 80/443

## Success Criteria
- `docker compose version` prints; `ss ... :80|:443` empty.

## Risk Assessment
- Low-medium. If 80/443 busy → Path B (nginx), don't force Caddy.

## Security Considerations
- Only 80/443 (+22 for SSH) exposed.

## Next steps
Phase 03: clone + config + run.
