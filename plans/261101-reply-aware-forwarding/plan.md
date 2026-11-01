# Plan: Reply-aware forwarding (preserve reply links + quote fallback)

Date: 2026-11-01 · Status: Ready for review · Priority: Medium-High

## Goal
When a source message is a **reply**, the forwarded copy in the destination is itself a reply to the
destination copy of the original. If the original has no forwarded copy → **quote** its content.
Mapping retained **3 days**.

## Locked design (research 01 API + 02 store)
- **Capture**: after each successful send, store `MessageMap(bot_id, dest_chat_id, source_chat_id,
  source_message_id) -> dest_message_id`. `copy_message` returns `MessageId.message_id`;
  `send_message` returns `Message.message_id`.
- **Resolve at SEND time** (worker): when a reply job runs, look up the dest copy of the replied-to
  source message. Per-dest job-id ordering guarantees the original was delivered+mapped first →
  correct even for fast back-to-back replies. (Build-time lookup would miss the race.)
- **Set reply**: `ReplyParameters(message_id=D, allow_sending_without_reply=True)` on copy/send
  (coexists with `message_thread_id` for forums; still sends if target was deleted).
- **Fallback (no map)**: prepend a quote `↳ <name>: <snippet>` — for `text` sends inline; for
  `copy`/`copy_caption` a short leading text, then the copy.
- **Retention**: periodic prune (worker, ~every 30-60 min) `DELETE FROM messagemap WHERE
  created_at < now-3d`; off the hot path. One extra INSERT per delivered message (WAL ok).
- **Atomicity**: worker inserts the map row in the SAME transaction as the job delete → a crash
  after send but before commit → Telegram redelivers? No (send already happened). So: delete job +
  insert map together AFTER a successful send; if that commit fails, at-worst a duplicate map row
  (no UNIQUE needed) — never a dropped/duplicated message.

## Phases
1. **phase-01-model-migration.md** — `MessageMap` + `ForwardJob` fields (origin_chat_id,
   origin_message_id, reply_to_source_message_id, reply_quote) + indexes + additive migration.
2. **phase-02-decision-reply.md** — decide_action extracts `reply_to_message` (R + name + snippet);
   build_jobs stamps origin + reply_to_source_message_id + reply_quote on every job (pure).
3. **phase-03-send-capture.md** — botcache.send_job accepts a resolved reply target + returns the
   new dest message_id (ReplyParameters); worker resolves the reply (map lookup), applies quote
   fallback, and stores the MessageMap on success (txn with job delete).
4. **phase-04-retention.md** — periodic 3-day prune in the worker dispatcher.
5. **phase-05-tests-docs.md** — reply-link e2e, fallback-quote, ordering, capture, prune; README+roadmap.

## Key files
- `models.py`, `db.py` (prune helper), `forwarding.py` (reply extract + job fields),
  `queue.py` (resolve + capture + store + prune), `botcache.py` (reply_parameters + return id),
  `webapp/tests/`, README/roadmap.

## Backward-compat
- Additive. Non-reply messages unaffected. Reply link is a send param (no content change) → works
  with existing copy/text/copy_caption + label + topic jobs.

## Open questions / decisions for reviewer
1. **Fallback for MEDIA replies** (copy/copy_caption, no map): send a short leading quote text then
   the media (recommended) vs forward plain without quote (simpler). Default: leading quote text.
2. **Quote snippet length** (e.g. 80 chars) + format `↳ <first_name>: <snippet>`. OK?
3. **Capture scope**: store a map row for EVERY delivered message (needed so any later reply can
   link). Accept the extra INSERT/row (bounded by 3-day prune). OK?
4. Only **1-level** replies are preserved (Telegram gives one level); nested chains link to their
   immediate parent. OK.
