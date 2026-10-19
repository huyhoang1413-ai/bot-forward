# Phase 02 — Decision layer (forwarding.py, pure)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01
- Research: [researcher-01-incoming-topics.md](./research/researcher-01-incoming-topics.md)

## Overview
- Date: 2026-10-19
- Description: Extract the source topic, skip forum service messages, match routes by (chat, thread), stamp each job's dest_thread_id, and make /chatid report + land in the topic. All pure/unit-tested.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Topic key: `message_thread_id` is reliable ONLY with `is_topic_message == True` (else false
  positives from non-forum reply threads). General → None.
- Match rule keeps NULL-source routes as "whole group" (all topics) for backward compat.
- Forum service messages must be skipped (they'd otherwise copy as "other").

## Requirements
- `decide_action` returns `source_thread_id` on forward/chatid/start actions.
- Forum service messages (`forum_topic_created/edited/closed/reopened`,
  `general_forum_topic_hidden/unhidden`) → `Action("skip")`.
- `select_destinations` returns `list[tuple[dest_chat_id, dest_thread_id]]` honoring the match rule.
- `build_jobs` stamps `dest_thread_id` on every job (copy/text/copy_caption/labeled).
- `/chatid` reply text includes the topic id when present, and the reply job targets that topic.

## Architecture
```python
# forwarding.py
_FORUM_SERVICE_KEYS = (
    "forum_topic_created", "forum_topic_edited", "forum_topic_closed",
    "forum_topic_reopened", "general_forum_topic_hidden", "general_forum_topic_unhidden",
)

def _topic_id(msg: dict) -> int | None:
    return msg.get("message_thread_id") if msg.get("is_topic_message") else None

@dataclass
class Action:
    kind: str
    source_chat_id: int | None = None
    message_id: int | None = None
    sender_username: str | None = None
    source_thread_id: int | None = None      # NEW

def decide_action(update, telegram_bot_id):
    msg = update.get("message") or update.get("edited_message")
    ...
    if any(k in msg for k in _FORUM_SERVICE_KEYS):
        return Action("skip")
    ...
    thread = _topic_id(msg)
    # chatid/start carry source_thread_id too (reply into same topic)
    return Action("forward", source_chat_id=source, message_id=...,
                  sender_username=..., source_thread_id=thread)

def select_destinations(routes, source_chat_id, source_thread_id):
    out = []
    for r in routes:
        if not r.enabled or r.source_chat_id != source_chat_id:
            continue
        if r.source_thread_id is None or r.source_thread_id == source_thread_id:
            out.append((r.dest_chat_id, r.dest_thread_id))
    return out
```
`build_jobs`: `for dest, dthread in select_destinations(routes, action.source_chat_id,
action.source_thread_id):` → pass `dthread` into `_copy_job/_text_job/_copy_caption_job/
build_labeled_jobs` (each gains a `dest_thread_id` arg written onto the ForwardJob).
`chatid` job: `dest_thread_id = action.source_thread_id`; text =
`f"chat_id: {src}"` + (`f"\nmessage_thread_id (topic): {thread}"` if thread is not None).
`start` reply likewise targets the source topic.

## Related code files
- `webapp/app/forwarding.py` — `_topic_id`, service skip, Action field, select_destinations,
  build_jobs + the 3 job builders + build_labeled_jobs.

## Implementation Steps
1. Add `_topic_id`, `_FORUM_SERVICE_KEYS`, Action.source_thread_id.
2. decide_action: skip service msgs; set source_thread_id.
3. select_destinations: new signature + match rule; update build_jobs loop.
4. Thread dest_thread_id through all job builders.
5. /chatid + /start reply topic.
6. Pure unit tests.

## Todo list
- [ ] topic extraction + service-message skip
- [ ] select_destinations (chat,thread) match rule
- [ ] dest_thread_id on all job builders
- [ ] /chatid topic reply
- [ ] forwarding unit tests

## Success Criteria
- Topic msg → only the matching topic route(s) fire; NULL-source route still forwards any topic.
- Non-forum reply (message_thread_id set, is_topic_message false) → treated as None (no false route).
- Forum service message → no jobs.
- Labeled/caption/copy jobs all carry the right dest_thread_id.

## Risk Assessment
- Medium. `select_destinations` signature change ripples into build_jobs + tests. Keep the pure
  layer fully covered. Watch the General ambiguity (None matches NULL routes only).

## Security Considerations
- None new (pure logic). Service-message skip avoids leaking topic admin events downstream.

## Next steps
Phase 03 delivers dest_thread_id to Telegram.
