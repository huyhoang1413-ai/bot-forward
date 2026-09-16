# Scout Report 01 — Files impacted by "global list + per-group assignment"

Author: main agent (firsthand — all files edited this session). Scope: webapp/.

## Current state (after commit 7b1b303 "global allowlist per bot")
Allowlist is now GLOBAL per bot. `AllowedSender(bot_id, source_chat_id=0, username, label)`.
`source_chat_id` fixed to sentinel `GLOBAL_SOURCE=0`. Group section only shows routes.

## Key files + roles

### Data / models
- `webapp/app/models.py`
  - `GLOBAL_SOURCE = 0` sentinel (L~45).
  - `AllowedSender` (L~48-70): `id, bot_id, source_chat_id(default 0), username, label, created_at`.
    UniqueConstraint `(bot_id, source_chat_id, username)` name `uq_allowed_sender`.
  - `Route` (L34-42): `id, bot_id, source_chat_id, dest_chat_id, enabled, created_at`.
  - `ForwardJob` outbox (unchanged, irrelevant here).

### Migration
- `webapp/app/db.py`
  - `create_db_and_tables()` (L39-42) → `_add_missing_columns()` (additive ADD COLUMN only)
    + `_collapse_allowed_senders_to_global()` (L~73-108, one-time collapse to source=0).
  - Migration convention: **additive only** (nullable/default cols). Destructive schema change (drop col / new NOT NULL) NOT supported by helper → must be nullable/defaulted or need new table.

### Forwarding logic (pure, unit-tested)
- `webapp/app/forwarding.py`
  - `build_jobs(update, telegram_bot_id, routes, bot_id, allowed_senders: dict[str,str|None]|None)` (L205-263).
    Gate: `is_sender_allowed(sender_username, set(allowed.keys()))` (L179-187) — empty=allow all.
    Label lookup: `allowed.get(sender_username)`. Per-dest jobs via `select_destinations(routes, source)` (L190-196).
  - `decide_action` (L143-176) extracts `source_chat_id`, `sender_username`.
  - THIS is where per-group scoping must be applied (currently single global map, source-agnostic).

### Webhook (builds the map)
- `webapp/app/webhook.py` (L30-56)
  - Builds `allowed_senders = {row.username: row.label}` from all bot rows, passes to `build_jobs`.
  - To support per-group: needs source→sender scoping data available here.

### Services (DB ops)
- `webapp/app/services.py`
  - `add_allowed_sender(session, bot_id, username, label)` (L141-175) global upsert on (bot_id,0,username).
  - `delete_allowed_sender(session, allowed_id, bot_id)` (L211-217) by id, bot-scoped (IDOR guard).
  - `update_allowed_label(...)` (L200-208).
  - `add_route / delete_route` (L103-138) — source group lifecycle.

### UI (server-rendered)
- `webapp/app/ui.py`
  - `bot_detail` (L112-144): loads `routes`, `source_groups` (distinct), `allowed_senders` list → template.
  - `create_allowed` (L~180-198): POST username+label → global add.
  - `remove_allowed`, `edit_allowed_label`, route CRUD endpoints.
- `webapp/app/templates/bot_detail.html`
  - Card "Người gửi ... (áp dụng cho MỌI nhóm)" (global table + add form).
  - Card "Tuyến forward" — per source-group `<details>`, routes only. **This is where per-group assignment UI would go.**

### Tests (real DB, no mocks) — must extend
- `tests/test_forwarding.py` — build_jobs gating/labels (global map).
- `tests/test_services.py` — add/delete/update allowed.
- `tests/test_ui_allowed.py`, `tests/test_ui_labels.py` — UI POST flows.
- `tests/test_webhook.py` — secret only.
- `conftest.py` — temp sqlite, `create_db_and_tables()` session fixture.

## Conventions to respect
- Pure decision layer in forwarding.py (no network) — keep testable.
- Additive SQLite migration only; new tables OK via `create_all`.
- Empty allowlist = forward everyone (backward-compat rule — must preserve semantics decision).
- IDOR guards: all mutations scoped by bot_id.
- No mocks in tests; Vietnamese UI strings, English code/comments.

## Open questions for design
- Semantics when a sender has NO group assignment (forward nowhere? everywhere?).
- Semantics when a GROUP has no assigned senders (forward everyone? = current empty rule).
- Per-group nickname override vs single global nickname (user picked assignment; label override TBD).
