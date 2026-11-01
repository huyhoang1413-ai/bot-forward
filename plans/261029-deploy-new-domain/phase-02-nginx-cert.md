# Phase 02 — nginx vhost + Let's Encrypt cert

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (DNS resolves)

## Overview
- Date: 2026-10-29
- Description: Add a host-nginx server block for `<newdomain>` that reverse-proxies to the app, then issue TLS with certbot. (Scenario C proxies to a NEW port instead.)
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Reuse the existing pattern (`bots.wefunmedia.com` vhost). nginx already owns 80/443.
- A/B proxy to `127.0.0.1:8000` (same app). C proxies to `127.0.0.1:8001` (second instance, phase-03).

## Requirements
- `https://<newdomain>` serves the app with a valid Let's Encrypt cert; HTTP→HTTPS redirect.

## Architecture
```bash
# on VPS
sudo tee /etc/nginx/sites-available/<newdomain> >/dev/null <<'EOF'
server {
    listen 80;
    server_name <newdomain>;
    location / {
        proxy_pass http://127.0.0.1:8000;   # C: 8001
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF
sudo ln -sf /etc/nginx/sites-available/<newdomain> /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx
sudo certbot --nginx -d <newdomain>      # email, agree, choose redirect (2)
```

## Related code files
- `/etc/nginx/sites-available/<newdomain>` (new).

## Implementation Steps
1. Write the vhost (port 8000 for A/B; 8001 for C).
2. `nginx -t` → reload.
3. `certbot --nginx -d <newdomain>` (installs cert + 443 + redirect; auto-renew via timer).

## Todo list
- [ ] vhost + enable + `nginx -t` OK
- [ ] certbot issues + deploys cert
- [ ] `curl -s https://<newdomain>/healthz` → `{"ok":true}` (A/B; C after phase-03)

## Success Criteria
- `https://<newdomain>` loads the panel with a trusted cert.

## Risk Assessment
- Medium: certbot fails if DNS not pointed/grey, or port 80 blocked. Confirm phase-01 first.
- Don't disturb existing vhosts; `nginx -t` before reload.

## Security Considerations
- TLS only (redirect 80→443). Same Secure-cookie behavior behind HTTPS.

## Next steps
Phase 03: app config for the chosen scenario.
