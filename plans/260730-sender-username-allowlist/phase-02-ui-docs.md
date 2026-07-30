# Phase 02 — Admin UI + Docs

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-backend-filter.md) (model + services)
- Research: [researcher-02](research/researcher-02-allowlist-design.md) (UX)
- Docs: Jinja2 https://jinja.palletsprojects.com/

## Overview
- **Date**: 2026-07-30
- **Description**: Add a per-source-group "Allowed senders" section to the bot detail page (add/remove usernames, "apply to both sides" helper), plus README/roadmap updates.
- **Priority**: High (makes the feature usable)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Source groups for a bot are derivable from its routes' `source_chat_id`s. Show one allowlist block per distinct source group.
- Bridges are the common case → offer an "apply to the reverse group too" checkbox so the admin sets both sides in one action ("cả 2 phía").
- Empty block must clearly read "No restriction — all senders forwarded" so behavior is obvious.
- Reuse existing Jinja + plain-form pattern; no new deps. Mutations must not touch the forwarding cache (webhook reads allowlist fresh per update).

## Requirements
- On `bot_detail.html`: for each distinct source `chat_id` in the bot's routes, render an "Allowed senders" list + add form (username input) + per-row remove.
- Add-form field: `username`, optional `both_ways` checkbox (adds to the reverse group if a reverse route exists).
- UI routes (admin-guarded), all redirect back to `/bots/{id}`:
  - `POST /bots/{bot_id}/allowed` (fields: `source_chat_id`, `username`, `both_ways?`)
  - `POST /bots/{bot_id}/allowed/{allowed_id}/delete`
- Validation: strip `@`, lowercase, regex `^[a-z0-9_]{5,32}$`; friendly error on invalid; dedup silently.
- Show usernames with a leading `@` (cosmetic).

## Architecture
```
webapp/app/
├── ui.py                       # + create_allowed / remove_allowed routes
└── templates/bot_detail.html   # + "Allowed senders" section per source group
```
Template sketch (per source group `g`):
```
Allowed senders — group {{ g }}
  {% for a in allowed[g] %} @{{ a.username }} [Remove] {% endfor %}
  {% if not allowed[g] %} No restriction — all senders forwarded {% endif %}
  <form POST /bots/{{bot.id}}/allowed>
     hidden source_chat_id={{ g }}; input username; [x] apply to both sides; [Add]
```
`ui.bot_detail` builds `source_groups` (distinct sources) + `allowed` (source_chat_id → rows).

## Related code files
- `webapp/app/ui.py`, `webapp/app/templates/bot_detail.html` (edit)
- Tests: `webapp/tests/test_ui_allowed.py` (new) or extend an existing UI test.

## Implementation Steps
1. `ui.bot_detail`: compute distinct source groups from routes + load `AllowedSender` grouped by source.
2. Add `POST /bots/{id}/allowed` (calls `services.add_allowed_sender`, honors `both_ways`) + validation/errors.
3. Add `POST /bots/{id}/allowed/{aid}/delete` (calls `services.delete_allowed_sender`).
4. Extend `bot_detail.html` with the per-group Allowed-senders section.
5. Manual click-through: add @user to group A with "both sides" → verify rows on A and B; send test messages → only allowed users forwarded.
6. Update `webapp/README.md` (feature + limits) and `docs/project-roadmap.md`.

## Todo list
- [ ] bot_detail loads source groups + allowlist
- [ ] add/remove allowed-sender routes + validation
- [ ] template section (per group) + "both sides" checkbox + empty-state copy
- [ ] UI test (add → appears; invalid → error; delete → gone)
- [ ] README + roadmap update

## Success Criteria
- Admin can add/remove allowed usernames per source group from the panel; "both sides" adds to the reverse group in one click.
- Invalid usernames rejected with a clear message; duplicates ignored.
- Empty state clearly says all senders are forwarded.
- End-to-end: after adding an allowlist, only listed users' messages forward (verified live).

## Risk Assessment
- **Low**: pure UI/CRUD. Main risk = source groups with no routes yet (nothing to show) → show hint to add a route first.

## Security Considerations
- All routes behind `require_admin`. Validate/normalize input server-side. Escape usernames in templates (Jinja autoescape).
- No token/secret exposure.

## Next steps
- Optional v2: user-id fallback for users without a username; per-route (finer than per-group) lists; blocklist mode; bulk paste import.
