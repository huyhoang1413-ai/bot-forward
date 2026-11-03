# Phase 01 — DNS

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)

## Overview
- Date: 2026-11-02
- Description: Point `<newdomain>` at the new VPS, DNS-only so Caddy can issue TLS.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Cloudflare "Proxied/orange" breaks Caddy's Let's Encrypt challenge → must be **DNS-only/grey**
  (same lesson as bots.wefunmedia.com). IPv4 A record; remove stray AAAA.

## Requirements
- `<newdomain>` resolves to `<VPS_IP>` from a public resolver.

## Architecture / Steps
1. DNS provider (Cloudflare if used): A `<newdomain>` = `<VPS_IP>`, proxy **DNS only (grey)**.
2. Verify: `nslookup <newdomain> 1.1.1.1` → returns `<VPS_IP>` (not a Cloudflare IP).

## Related code files
- None (DNS dashboard).

## Implementation Steps
1. Add A record (grey). 2. `nslookup <newdomain> 1.1.1.1` until it shows `<VPS_IP>`.

## Todo list
- [ ] A record `<newdomain>` → `<VPS_IP>` (grey)
- [ ] verify resolution = VPS IP

## Success Criteria
- `nslookup <newdomain> 1.1.1.1` → `<VPS_IP>`.

## Risk Assessment
- Low. Propagation delay (1–5 min); do NOT run Caddy until resolution is correct (else cert fails).

## Security Considerations
- None.

## Next steps
Phase 02: VPS + Docker.
