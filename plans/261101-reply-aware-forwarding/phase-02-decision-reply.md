# Phase 02 — Decision layer: extract reply + stamp jobs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01
- Research: [researcher-01-telegram-reply-api.md](./research/researcher-01-telegram-reply-api.md)

## Overview
- Date: 2026-11-01
- Description: Read `reply_to_message` from the update; carry the replied-to source id + a quote snippet; stamp origin + reply fields onto every ForwardJob (pure layer, unit-tested).
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `reply_to_message` carries `.message_id`, `.from.first_name`, `.text`/`.caption` (one level).
- Reply link is a send param → NO content change; only the fallback quote (phase-03) changes content.
- Every job must carry `origin_chat_id/origin_message_id` so the worker can store the map after send.

## Requirements
- `decide_action` → add `reply_to_source_message_id`, `reply_quote` to Action.
- `build_jobs` stamps `origin_chat_id`, `origin_message_id`, `reply_to_source_message_id`,
  `reply_quote` on each job (copy/text/copy_caption, labeled or not).

## Architecture
```python
# forwarding.decide_action (forward branch)
rtm = msg.get("reply_to_message") or {}
reply_id = rtm.get("message_id")          # None if not a reply
quote = None
if reply_id:
    name = (rtm.get("from") or {}).get("first_name") or "?"
    body = (rtm.get("text") or rtm.get("caption") or "").replace("\n", " ")
    quote = sanitize_quote(f"↳ {name}: {body}")   # clamp ~80-100 chars, strip control chars
Action(..., reply_to_source_message_id=reply_id, reply_quote=quote)

# build_jobs: on every emitted job set
job.origin_chat_id = action.source_chat_id
job.origin_message_id = action.message_id
job.reply_to_source_message_id = action.reply_to_source_message_id
job.reply_quote = action.reply_quote
```
Implementation: set these fields on each `ForwardJob` after creation in `build_jobs` (one small
helper `_stamp(job)` applied to every job before append), so copy/text/copy_caption + labeled
multi-job all carry them. `sanitize_quote` in forwarding (clamp length, drop `\r\n`, keep unicode).

## Related code files
- `webapp/app/forwarding.py` — Action fields, decide_action extract, `sanitize_quote`, build_jobs stamping.

## Implementation Steps
1. Action + decide_action reply extraction + sanitize_quote.
2. build_jobs: stamp origin + reply fields on every job.
3. Unit tests: reply extracted; quote clamped; non-reply → fields None; all job kinds stamped with origin.

## Todo list
- [ ] decide_action reply_to + quote + sanitize_quote
- [ ] build_jobs stamps origin + reply fields on all jobs
- [ ] forwarding unit tests

## Success Criteria
- A reply update yields jobs with `reply_to_source_message_id` set + a clamped `reply_quote`,
  and every job carries `origin_chat_id/origin_message_id`.
- Non-reply messages unchanged (reply fields None).

## Risk Assessment
- Low (pure). Careful: a reply to a BOT/own message still extracts an id — the worker's map lookup
  simply won't find it → fallback. Acceptable.

## Security Considerations
- Quote snippet is sanitized + length-clamped (untrusted content in a `↳` prefix).

## Next steps
Phase 03 resolves the link at send time + captures the map.
