# Phase 04 — Web UI (Dashboard, Add Bot, Routes, Chat-ID Helper)

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 02](phase-02-bot-lifecycle.md) (add/remove), [Phase 03](phase-03-webhook-forwarding.md) (cache invalidation)
- Research: [researcher-02](research/researcher-02-saas-architecture.md) (onboarding flow, server-rendered UI)
- Docs: Jinja2 https://jinja.palletsprojects.com/ ; HTMX https://htmx.org/

## Overview
- **Date**: 2026-07-27
- **Description**: Minimal server-rendered admin UI (Jinja2 + HTMX) behind login: list bots, add a bot by pasting a token, view/add/delete routes per bot, and a short onboarding guide for discovering chat ids.
- **Priority**: High (the actual product surface)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- KISS: a handful of pages, form posts, HTMX for inline add/delete without full reloads. No SPA/build step.
- The value prop = "paste token → works": the **Add Bot** form is the hero. After success, show next-step instructions (add bot as admin, /chatid, add route).
- All mutations must **invalidate the Phase-03 caches** so forwarding uses fresh routes.
- Directed routes; a "bidirectional" checkbox inserts both `A→B` and `B→A`.

## Requirements
- Pages (all require admin session):
  - `GET /` dashboard — list bots (username, status, #routes), remove button.
  - `POST /bots` — add bot from token (calls `services.add_bot`), flash errors (invalid/dup).
  - `GET /bots/{id}` — bot detail: routes list, add-route form, onboarding hints.
  - `POST /bots/{id}/routes` — add route (source, dest, bidirectional?) → invalidate cache.
  - `POST /bots/{id}/routes/{rid}/delete`, `POST /bots/{id}/delete`.
- `GET /login`, `POST /login`, `POST /logout` (from Phase 01 auth).
- Templates with a base layout; minimal CSS; HTMX for add/delete fragments.
- Input validation: token trimmed; chat ids parsed as int; friendly errors.

## Architecture
```
webapp/app/
├── ui.py                 # Jinja routes (dashboard, bot detail, forms)
└── templates/
    ├── base.html
    ├── login.html
    ├── dashboard.html
    ├── bot_detail.html
    └── _partials/…       # route row, bot row (HTMX targets)
```
Onboarding hints on `bot_detail.html`:
1. Add @{username} to your group as **admin**.
2. Send `/chatid` in the group → copy the id the bot replies.
3. Add a route (source id → dest id), tick *bidirectional* for a 2-way bridge.

## Related code files
- `webapp/app/ui.py`, `webapp/app/templates/*` (new)
- Calls `services.add_bot/remove_bot`, route CRUD on `models.Route`, `botcache.invalidate`.

## Implementation Steps
1. `base.html` + minimal CSS + HTMX include; `login.html`.
2. `dashboard.html` + `GET /` (list bots) + `POST /bots` (add) with error flashing.
3. `bot_detail.html` + `GET /bots/{id}` (routes + onboarding hints).
4. Route add/delete endpoints + HTMX partials; invalidate cache on each mutation.
5. Bot delete endpoint (confirm) → `services.remove_bot`.
6. Manual click-through of the full onboarding flow.

## Todo list
- [ ] base layout + login page + minimal CSS + HTMX
- [ ] dashboard: list bots + add-bot form (token) + errors
- [ ] bot detail: routes list + onboarding hints
- [ ] add/delete route (HTMX) + cache invalidation
- [ ] delete bot (confirm)
- [ ] end-to-end click-through

## Success Criteria
- Admin logs in, pastes a valid token, sees the new bot listed with its username.
- Adding a route makes forwarding work immediately (no restart); deleting it stops forwarding.
- Bidirectional checkbox creates two working directions.
- Invalid token / bad chat id show a clear inline error.
- Unauthenticated access to any page redirects to `/login`.

## Risk Assessment
- **Low**: template/UX polish. Keep styling minimal.
- **Medium**: forgetting cache invalidation → edits not taking effect; covered in steps + tests.

## Security Considerations
- All routes guarded by `require_admin`. CSRF: same-site cookie + POST-only mutations (add CSRF token if exposed publicly).
- Never render the token back into HTML (show only username / masked).
- Escape all user-provided values in templates (Jinja autoescape on).

## Next steps
Proceed to [Phase 05](phase-05-deploy-tests-docs.md) — containerize, TLS, tests, docs.
