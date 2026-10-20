# Plan: Auto-nickname from Telegram name (capture-once first_name, everyone)

Date: 2026-10-20 · Status: Ready for review · Priority: Medium

## Goal
Let the bot auto-use a sender's Telegram **first_name** as the forward nickname — **captured once**
per user (stored, admin-editable), applied to **everyone** (even when the allowlist is empty).
Per-bot toggle. No manual typing needed.

## Locked design (from research 01 identity + 02 storage)
- **Identity**: key by `from.id` (user_id); `from.first_name` always present for real users.
  `from` absent (anonymous admin / channel post / auto-forward) → no auto-nick (skip capture).
  Label the in-group sender (`from`), not forwarded origin.
- **Store**: new `SenderProfile(bot_id, telegram_user_id, first_name, label_override, username,
  captured_at)` UNIQUE(bot_id, user_id). `first_name` = captured once (never overwritten);
  `label_override` = admin edit; `username` may refresh.
- **Capture-once**: SQLite `insert().on_conflict_do_nothing()` + a per-process seen-cache
  `set[(bot_id,user_id)]` so repeat senders skip the DB. Capture ALWAYS (even if auto_nick off)
  so toggling on works retroactively.
- **Per-bot flag**: `Bot.auto_nick: bool = False` (additive).
- **Label precedence (per message)**: manual `AllowedSender.label` (by username) >
  `SenderProfile.label_override` > `SenderProfile.first_name` (only if `bot.auto_nick`) > None.
  Resolved in webhook; profile SELECT only when auto_nick on AND no manual label.
- **build_jobs**: replace `label_map` with a single resolved `label: str|None` for THIS message;
  gating unchanged; `build_labeled_jobs` reused (UTF-16 entity shifting handles any name).
- **Proactive lookup** (getChatMember) → deferred ("refresh names" button, future).

## Phases (each independently testable)
1. **phase-01-model-migration.md** — `Bot.auto_nick` + `SenderProfile` + additive migration.
2. **phase-02-capture.md** — decide_action extracts user_id+first_name; webhook capture-once
   (on_conflict + seen-cache); `services.capture_sender`.
3. **phase-03-label-resolution.md** — resolve effective label per message (precedence);
   build_jobs takes `label` (drop label_map). Pure + webhook tests.
4. **phase-04-ui.md** — bot_detail "Tự động gắn tên người gửi" toggle; "Tên đã ghi nhận" page
   (list/search/paginate, edit override, delete).
5. **phase-05-tests-docs.md** — end-to-end (auto-nick on → first message prefixes first_name;
   override wins; off → none), README + roadmap.

## Key files
- `models.py`, `db.py`, `forwarding.py`, `webhook.py`, `services.py`, `ui.py`,
  `templates/bot_detail.html` + new profiles template, `webapp/tests/`.

## Backward-compat
- Additive only. `auto_nick` defaults False → no behavior change until toggled. Existing manual
  username-labels keep working and still win. Webhook/gating unchanged.

## Open questions / decisions for reviewer
1. **Capture even when auto_nick OFF** (populate history for retroactive toggle) — recommended. OK?
2. **Precedence**: manual username-label beats captured name (keeps today's labels). OK?
3. **Bots as senders** (`is_bot`): capture too (simpler). OK, or skip bots?
4. **first_name is frozen** (capture-once); to always use the live current name you'd want the
   "dynamic" option (not chosen). Confirm frozen + editable is intended.
