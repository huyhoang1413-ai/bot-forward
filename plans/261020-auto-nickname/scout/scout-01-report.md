# Scout Report 01 — Auto-nickname from Telegram name (capture-once, first_name, everyone)

Author: main agent (firsthand). Scope: webapp/.

## Locked requirements (user)
- **Capture once** the sender's Telegram **first_name**, store it, editable in UI.
- Apply to **everyone** (even when allowlist empty / forward-everyone), not just allowlisted.
- Per-bot opt-in toggle implied (don't force prefix on bots that don't want it).

## Current labeling pipeline (what exists)
- `AllowedSender(bot_id, source_chat_id=GLOBAL_SOURCE(0), username, label)` — the allowlist +
  a MANUAL label, keyed by **username**. Labels only exist for allowlisted usernames.
- `webhook.py`: builds `label_map = {username: label}` (bot-wide) + `allowed_by_source`
  (per-group gating sets) + `gate_active`; calls `build_jobs(...)`.
- `forwarding.decide_action(update, tg_bot_id)` → `Action(kind, source_chat_id, message_id,
  sender_username, source_thread_id)`. It reads `from.username` ONLY — NOT `from.id` or `first_name`.
- `forwarding.build_jobs(...)`: gates by `allowed_by_source`; `label = label_map.get(sender_username)`;
  prefixes via `build_labeled_jobs` (UTF-16 entity-offset shifting; text→send_message,
  caption media→copy_message caption override, caption-less→`[label]` line, over-limit→plain copy).
- Sender identity today = **username**. Users WITHOUT a username can't be labeled.

## Why this feature needs a new identity + store
- "Everyone" incl. users with NO username → must key by **telegram user_id** (`from.id`).
- first_name comes ONLY from messages (Bot API can't look up a name by username) → **capture on
  message**. "Capture once" = store on first sight, don't overwrite; admin can override.

## Proposed design (for planner)
1. **Model**:
   - `Bot.auto_nick: bool = False` (per-bot toggle; additive nullable/defaulted).
   - New `SenderProfile(id, bot_id, telegram_user_id, first_name, label_override, username,
     captured_at)`, UniqueConstraint(bot_id, telegram_user_id). `first_name` = captured-once auto
     nick; `label_override` = admin edit.
2. **decide_action**: also extract `sender_user_id = from.id` and `sender_first_name = from.first_name`
   (add to Action). No `from` (channel/anonymous) → both None (no auto-nick; see research).
3. **Capture (webhook, write path)**: on a forward with sender_user_id+first_name, **upsert-once**
   into SenderProfile (INSERT-or-ignore; keep first captured name; optionally refresh username).
   Use a per-process seen-cache to avoid a write every message.
4. **Label resolution (per message)**: precedence
   `AllowedSender.label (manual, by username)` > `SenderProfile.label_override` >
   `SenderProfile.first_name` (only if `bot.auto_nick`) > None.
   Resolve in webhook (it has the DB + the one sender), pass a single `label: str|None` to build_jobs.
5. **build_jobs**: replace `label_map` with a resolved `label: str | None` for THIS message
   (webhook computed it). Gating (`allowed_by_source`/`gate_active`) unchanged. `build_labeled_jobs`
   reused as-is (handles any `[name]` incl. emoji/unicode).
6. **UI**: a per-bot "Tự động gắn tên người gửi" toggle; a "Tên đã ghi nhận" page (list captured
   SenderProfile rows: user_id, @username, first_name, [override], delete) — paginated/searchable
   like the senders page (reuse patterns). Editing sets label_override; delete removes the row.
7. **Migration**: additive — `Bot.auto_nick` via `_add_missing_columns`; `SenderProfile` via create_all.

## Files to touch
- `models.py` (Bot.auto_nick + SenderProfile), `db.py` (auto index optional), `forwarding.py`
  (Action fields, build_jobs label), `webhook.py` (capture + resolve label), `services.py`
  (capture upsert, profile CRUD/search, label resolution helper), `ui.py` (toggle + profiles page),
  `templates/` (bot_detail toggle + new profiles template), tests.

## Open questions for design (research resolves)
- Exact `from` presence: channel posts / anonymous admins (`sender_chat`) / automatic forwards —
  do they have `from`/`first_name`? (→ no auto-nick for them; confirm.) Forwarded msgs: label the
  in-group SENDER (`from`), not `forward_from`. Confirm.
- Is there ANY Bot API way to fetch a member's name proactively (e.g. getChatMember by user_id)?
  (Alternative to capture-on-message; may enable a "refresh names" button later.)
- Capture-once upsert pattern in SQLite/SQLModel (INSERT OR IGNORE / ON CONFLICT DO NOTHING) +
  cache to avoid per-message writes.
- Precedence vs the existing username-based manual labels (avoid double-labeling).
