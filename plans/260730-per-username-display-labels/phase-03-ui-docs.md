# Phase 03 — Admin UI + Docs

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-model-services.md) (services), [Phase 02](phase-02-labeled-forwarding.md) (behavior)
- Research: [researcher-02](research/researcher-02-label-design.md) (UX)
- Docs: Jinja2 https://jinja.palletsprojects.com/

## Overview
- **Date**: 2026-07-30
- **Description**: Add a "Sender labels" section to the bot detail page to set/edit/clear a display name per username, plus README/roadmap updates.
- **Priority**: High (makes the feature usable)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Labels are per-bot (username → label), independent of the allowlist, so this is a single section on the bot page (not per source group).
- Reuse existing Jinja + plain-form pattern; one row per label with an inline edit + clear, plus an "add" form (username + label).
- Setting a blank label removes it (matches service behavior) — gives an easy "clear".
- Mutations don't need cache invalidation (webhook reads labels fresh per update).

## Requirements
- On `bot_detail.html`: a "Nhãn người gửi (labels)" section listing current `SenderLabel` rows (`@username → [label]`), each with edit (label input + save) and remove; plus an add form (`username`, `label`).
- UI routes (admin-guarded), redirect back to `/bots/{id}`:
  - `POST /bots/{bot_id}/labels` (fields `username`, `label`) → `services.set_label` (validates; blank label deletes).
  - `POST /bots/{bot_id}/labels/{label_id}/delete` → `services.delete_label`.
- Validation errors (`bad_username`, `bad_label`) surfaced via `?error=` like existing patterns.
- Show a hint: “Nhãn hiển thị dạng `[Tên] nội dung`. Áp dụng cho mọi nhóm của bot.”

## Architecture
```
webapp/app/
├── ui.py                        # + set_label / remove_label routes; load labels in bot_detail
└── templates/bot_detail.html    # + "Sender labels" section
```
`ui.bot_detail` additionally loads `labels = SenderLabel rows for bot`.

## Related code files
- `webapp/app/ui.py`, `webapp/app/templates/bot_detail.html` (edit)
- Tests: `webapp/tests/test_ui_labels.py` (new)

## Implementation Steps
1. `ui.bot_detail`: load labels for the bot.
2. `POST /bots/{id}/labels` (add/update via `set_label`, validate username + label) + `?error` handling.
3. `POST /bots/{id}/labels/{id}/delete`.
4. Template "Sender labels" section (list + add/edit + remove) with the hint + empty state.
5. UI test: add label → appears; invalid → error; blank label → removed; auth required.
6. Update `webapp/README.md` (feature + format + limits) and `docs/project-roadmap.md`.

## Todo list
- [ ] bot_detail loads labels
- [ ] add/update + delete label routes + validation
- [ ] template section (list + add/edit + remove + hint)
- [ ] UI test (add/invalid/blank-removes/auth)
- [ ] README + roadmap

## Success Criteria
- Admin can set `@fbagency999 → Doby`, see it listed, edit, and clear it, from the panel.
- After setting, forwarded messages from that user show `[Doby] …` (verified live).
- Invalid username/label rejected with a clear message.
- Unauthenticated access redirects to `/login`.

## Risk Assessment
- **Low**: UI/CRUD only.

## Security Considerations
- Behind `require_admin`; server-side validate/normalize; Jinja autoescape on; scoped deletes.

## Next steps
- Optional v2: per-source-group label overrides, suffix/footer, configurable template (`{name}: {text}`), label by user-id.
