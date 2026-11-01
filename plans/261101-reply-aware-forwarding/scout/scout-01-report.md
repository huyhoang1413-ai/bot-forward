# Scout Report 01 — Reply-aware forwarding (preserve reply links)

Author: main agent (firsthand). Scope: webapp/.

## Locked requirements (user)
- **Preserve the real reply link**: a forwarded reply is itself a reply to the corresponding
  forwarded copy of the original message in the destination.
- **Fallback = quote** the replied-to content when the original has no forwarded copy (allowlist-
  blocked / too old / before feature).
- **Retention = 3 days** for the message-id mapping.

## Current pipeline (what exists)
- `forwarding.decide_action(update, tg_bot_id)` → Action(source_chat_id, message_id,
  sender_username, source_thread_id, sender_user_id, sender_first_name). **Does NOT read
  `reply_to_message`.**
- `forwarding.build_jobs(update, tg_id, routes, bot_id, allowed_by_source, label, gate_active)`
  (pure) → `ForwardJob` rows, one per dest, via `select_destinations` (returns (dest_chat, dest_thread)).
  Kinds: `copy` (copy_message), `text` (send_message, for labeled text), `copy_caption`.
- `ForwardJob(bot_id, dest_chat_id, dest_thread_id, kind, from_chat_id, message_id, text,
  entities_json, caption, caption_entities_json, status, attempts, next_attempt_at, ...)`.
  For `copy`: from_chat_id=source, message_id=source msg id. For `text`/`copy_caption`:
  from_chat_id/message_id may be None (reconstructed).
- `queue.Worker`: per-dest sequential by job id (preserves order); calls `send_fn(job_dict)` then
  deletes the job. **Discards the send result** (no dest message_id captured). `_job_to_dict` maps fields.
- `botcache.send_job(job)`: calls `bot.copy_message(...)` / `bot.send_message(...)` /
  `bot.copy_message(caption=...)` with `message_thread_id=mt`. **Returns None** (result discarded).
  BadRequest/Forbidden → PermanentSendError (fail fast). AIORateLimiter paces.

## What's missing for reply-awareness
1. **Capture** the delivered message_id: send_job must RETURN the new dest message_id
   (copy_message returns `MessageId`; send_message returns full `Message`). Worker stores a mapping.
2. **MessageMap** table: (bot_id, dest_chat_id, source_chat_id, source_message_id) -> dest_message_id,
   created_at. Lookup index + created_at index (pruning). 3-day retention prune.
3. **ForwardJob new fields**: `origin_chat_id`, `origin_message_id` (the SOURCE message being
   forwarded, set for ALL kinds — needed to store the mapping after any send); and
   `reply_to_message_id` (the resolved DEST message id to reply to, or None).
4. **decide_action**: extract `reply_to_message` → its message_id (R, in source chat) + a content
   snippet + sender first_name (for the quote fallback). Ignore replies whose reply_to is a
   channel/forward origin (only in-group replies).
5. **Resolution (webhook, DB)**: for each dest the msg goes to, look up MessageMap(bot, dest,
   source, R). Build `reply_target_by_dest={dest: dest_msg_id}`. Pass to build_jobs:
   - dest found → set job.reply_to_message_id (reply LINK; no content change — compatible with label).
   - dest not found but R exists → QUOTE fallback (emit a leading quote, then content).
   Resolve at build time (original almost always delivered before the reply; per-dest ordering).
6. **send_job**: pass `reply_to_message_id` via `reply_parameters` with
   `allow_sending_without_reply=True` (so a since-deleted target still sends), together with
   `message_thread_id` (forum: reply must be in the same topic — research confirms).

## Reuse / compatibility
- Reply LINK is just a send param → works with existing `copy`/`text`/`copy_caption` + label +
  topic jobs with NO content change. Only the QUOTE fallback changes content (keep it simple:
  a leading "↳ <name>: <snippet>" text job, then the normal content job — mirrors the labeled
  "other" two-job pattern).
- Ordering: worker processes a dest's jobs in id order → the original (smaller id) is delivered
  and mapped before the reply's job → mapping present at reply send/resolve time.

## Files to touch
- `models.py` (MessageMap + ForwardJob fields), `db.py` (prune helper), `forwarding.py`
  (decide_action reply extract + build_jobs reply param/quote), `webhook.py` (resolve
  reply_target_by_dest + quote data), `queue.py` (capture result -> store MessageMap + periodic
  prune), `botcache.py` (return dest message_id + reply_parameters), tests, README/roadmap.

## Open questions (research resolves)
- python-telegram-bot v21: `reply_parameters=ReplyParameters(message_id, allow_sending_without_reply)`
  vs deprecated `reply_to_message_id`; return types; forum topic + reply interaction; native `quote`.
- MessageMap write volume + SQLite pruning pattern at 3-day retention; dedupe (same src msg -> many dests).
- Edge: media groups/albums (separate messages), edited replies, service messages.
