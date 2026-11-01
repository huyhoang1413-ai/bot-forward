# Phase 01 — DNS: point the new domain at the VPS

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)

## Overview
- Date: 2026-10-29
- Description: Create an A record for `<newdomain>` → `103.179.184.26`, DNS-only (no proxy) so certbot HTTP-01 can issue a cert.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Cloudflare "Proxied/orange" breaks certbot HTTP-01 → must be **DNS-only/grey** (same lesson as the first deploy). IPv4 only (A record); remove any AAAA pointing elsewhere.

## Requirements
- `<newdomain>` resolves to `103.179.184.26` from a public resolver.

## Architecture / Steps
1. In the DNS provider (Cloudflare if used): add **A** `<newdomain>` = `103.179.184.26`,
   proxy status **DNS only (grey)**. Remove AAAA if present.
2. Verify (local): `nslookup <newdomain> 1.1.1.1` → must return `103.179.184.26` only.

## Related code files
- None (DNS provider dashboard).

## Implementation Steps
1. Add A record (grey).
2. `ipconfig /flushdns` then `nslookup <newdomain> 1.1.1.1` until it returns the VPS IP.

## Todo list
- [ ] A record `<newdomain>` → 103.179.184.26 (grey)
- [ ] verify resolution = VPS IP (not Cloudflare)

## Success Criteria
- `nslookup <newdomain> 1.1.1.1` → `103.179.184.26`.

## Risk Assessment
- Low. Propagation delay (1–5 min). Do NOT proceed to certbot until resolution is correct.

## Security Considerations
- None.

## Next steps
Phase 02: nginx vhost + TLS.
