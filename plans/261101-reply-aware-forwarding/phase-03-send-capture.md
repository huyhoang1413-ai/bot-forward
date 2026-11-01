# Phase 03 — Send-time resolve + capture map

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02
- Research: [researcher-01-telegram-reply-api.md](./research/researcher-01-telegram-reply-api.md),
  [researcher-02-mapping-store.md](./research/researcher-02-mapping-store.md)

## Overview
- Date: 2026-11-01
- Description: At send time, resolve the dest reply target from MessageMap; set ReplyParameters (or apply the quote fallback); capture the returned dest message_id and store the map atomically with the job delete.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Per-dest job-id ordering ⇒ the original's job (smaller id) is delivered + mapped BEFORE the reply's
  job ⇒ send-time lookup is correct even for fast replies.
- Keep `botcache.send_job` a thin Telegram wrapper (reply target passed in, returns dest id); the
  WORKER owns DB (map lookup + store) so the txn wraps store+delete.
- `allow_sending_without_reply=True` ⇒ a since-deleted target still sends (as non-reply).

## Requirements
- Worker resolves `reply_to_message_id` for a job (map lookup by bot/dest/source/reply_to_source).
- `send_job` sets `reply_parameters` + returns the new dest message_id; applies quote fallback when
  no map.
- On success: store `MessageMap(origin → dest)` + delete the job in one transaction.

## Architecture
```python
# queue.Worker._process_chat (success path)
job = head
reply_to = None
if job["reply_to_source_message_id"]:
    reply_to = _lookup_map(job["bot_id"], job["dest_chat_id"],
                           job["origin_chat_id"], job["reply_to_source_message_id"])  # -> dest id or None
job["reply_to_message_id"] = reply_to          # None -> fallback/quote in send_job
dest_msg_id = await self._send_fn(job)          # returns int message_id
with Session(engine) as s:                      # one txn: store map + delete job
    if dest_msg_id and job["origin_message_id"]:
        s.add(MessageMap(bot_id=job["bot_id"], dest_chat_id=job["dest_chat_id"],
              source_chat_id=job["origin_chat_id"], source_message_id=job["origin_message_id"],
              dest_message_id=dest_msg_id))
    j = s.get(ForwardJob, job["id"]);  s.delete(j) if j else None
    s.commit()

# botcache.send_job  -> return the dest message id; set reply + quote fallback
mt = job.get("dest_thread_id"); reply_id = job.get("reply_to_message_id")
rp = ReplyParameters(message_id=reply_id, allow_sending_without_reply=True) if reply_id else None
quote = job.get("reply_quote")
if kind == "text":
    text = job["text"]
    if reply_id is None and quote: text = quote + "\n" + text      # fallback prepend
    m = await bot.send_message(chat_id=..., text=text, entities=..., message_thread_id=mt,
                               reply_parameters=rp)
    return m.message_id
elif kind in ("copy","copy_caption"):
    if reply_id is None and quote:                                 # fallback: lead quote, then copy
        await bot.send_message(chat_id=job["dest_chat_id"], text=quote, message_thread_id=mt)
    mid = await bot.copy_message(..., message_thread_id=mt, reply_parameters=rp, caption=...)
    return mid.message_id
```
`_job_to_dict` must include the new fields (origin_*, reply_to_source_message_id, reply_quote).
Worker needs `engine` (already importable) + `MessageMap` import.

## Related code files
- `webapp/app/botcache.py` — ReplyParameters, quote fallback, return message id.
- `webapp/app/queue.py` — `_lookup_map`, set reply target, store map + delete in one txn, `_job_to_dict`.

## Implementation Steps
1. botcache: import ReplyParameters; return dest id; reply + quote fallback per kind.
2. queue: `_lookup_map`; set `reply_to_message_id`; after send, store MessageMap + delete job txn.
3. `_job_to_dict` carries new fields.
4. Tests (phase-05): map lookup, link set, fallback, capture, ordering.

## Success Criteria
- Reply whose original was forwarded → dest copy is a reply to the right dest message.
- Original not forwarded → dest copy carries the `↳` quote; message still delivered.
- A MessageMap row is written for each delivered message (verified).

## Risk Assessment
- Medium (hot path + ordering). Map store must not drop/duplicate the job: send first, then
  store+delete; a crash before commit → job stays pending → redeliver (one duplicate send possible,
  same as today's at-least-once). Keep behavior documented.
- `copy_message` return attr is `MessageId.message_id`; `send_message` is `Message.message_id`.

## Security Considerations
- Quote is sanitized (phase-02). allow_sending_without_reply avoids leaking by erroring.

## Next steps
Phase 04 prunes the map.
