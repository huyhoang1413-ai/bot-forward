# Scout Report 01 — Scaling sender allowlist UI to 500-1000 senders

Author: main agent (firsthand — implemented current feature). Scope: webapp/.

## Problem
Current per-group assignment UI renders EVERY sender as a checkbox inside EVERY group's
`<details>` block (`bot_detail.html`). With 500-1000 senders × N groups → thousands of
checkboxes per page → unusable. The global sender card also renders ALL rows in one table.
**Data model already scales; the bottleneck is UI (render-all) + no search/pagination.**

## Current data model (already fine for scale)
- `AllowedSender(id, bot_id, source_chat_id=0 sentinel, username, label, created_at)`
  — registry, UniqueConstraint (bot_id, source_chat_id, username). Index on bot_id, source_chat_id.
- `SenderGroupAssignment(id, allowed_sender_id FK, source_chat_id, created_at)`
  — junction. UniqueConstraint (allowed_sender_id, source_chat_id); Index (source_chat_id, allowed_sender_id).
- `Route(bot_id, source_chat_id, dest_chat_id, enabled)`.
Junction supports per-group DISTINCT lists efficiently. Keep it.

## Files + current behavior
### UI (the part to overhaul)
- `webapp/app/ui.py`
  - `bot_detail` (L112-160ish): loads ALL `allowed_senders` + builds `assigned_by_group: {source: set(sender_id)}` from ALL assignments. Passes everything to template → render-all.
  - `create_allowed` (POST /bots/{id}/allowed): add one sender (username+label) global.
  - `remove_allowed`, `edit_allowed_label`.
  - `set_group_senders` (POST /bots/{id}/groups/{source}/senders): replace-all from `sender_ids[]` checkboxes.
- `webapp/app/templates/bot_detail.html`
  - Card "Người gửi (danh sách chung)": full table of all senders + add form.
  - Per-group `<details>`: `<fieldset>` with a checkbox PER sender (the scale killer) + Lưu.

### Forwarding (already scale-safe)
- `webapp/app/webhook.py`: 2 queries — senders of bot (label_map, by_id), assignments via
  `allowed_sender_id.in_(ids)` → `allowed_by_source`. O(1) set-membership gate in build_jobs.
  At 1000 senders this is one IN-list of 1000 ids; acceptable but see research (chunking / join).
- `webapp/app/forwarding.py`: `build_jobs(..., allowed_by_source, label_map, gate_active)` pure.

### Services
- `webapp/app/services.py`: `add_allowed_sender`, `delete_allowed_sender` (cascades assignments),
  `set_group_senders` (replace-all, bot-scoped), cascade in remove_bot/delete_route.
- `webapp/app/botcache.py`: per-bot ExtBot cache (exists; not for senders yet).

### DB / migration
- `webapp/app/db.py`: additive migrations only (ADD COLUMN); `create_all` for new tables;
  one-time idempotent data migrations pattern. WAL enabled.

### Tests
- `tests/test_ui_allowed.py`, `test_ui_labels.py`, `test_ui_group_senders.py`, `test_services.py`,
  `test_forwarding.py`, `test_migration.py`. Real sqlite, no mocks. 89 pass currently.

## What must change (scale)
1. Stop rendering all senders. Add SERVER-SIDE search (LIKE on username/label) + pagination
   (query params) for: (a) the registry list, (b) each group's assigned-senders list.
2. Per-group assignment: replace checkbox-matrix with add-via-search + paginated assigned list
   with per-row remove. Likely a DEDICATED page `/bots/{id}/groups/{source}/senders`.
3. Index for search: `AllowedSender.username` already unique-constrained (indexable); confirm a
   usable index for `LIKE 'q%'` prefix search (lowercased). Possibly add index on (bot_id, username).
4. Replace `set_group_senders` replace-all-from-full-form with incremental add/remove endpoints
   (add_group_sender / remove_group_sender) so we never post the whole list.

## Constraints to respect
- Plain server-rendered (Jinja2) + FastAPI forms. Minimal JS acceptable (user OK'd JS for search).
- No mocks in tests. Vietnamese UI, English code.
- Keep webhook hot path ≤2 queries, no N+1.
- Additive migrations only.

## Open questions for design
- Dedicated per-group page vs inline search within `<details>`.
- Pagination style: offset (simple) vs keyset (faster at scale). 1000 rows → offset is fine.
- Optional bulk import (paste/CSV) — user chose search+add lẻ; treat bulk as deferred/optional.
- Do we still need the global registry card, or manage senders only per-group? (Registry gives
  DRY nicknames; lists differ per group but a person may recur → keep registry + assignment.)
