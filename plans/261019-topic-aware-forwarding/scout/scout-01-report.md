# Scout Report 01 — Topic-aware forwarding (per source/dest topic pair)

Author: main agent (firsthand). Scope: webapp/. Current code has ZERO topic handling
(grep `message_thread_id|thread|topic|forum` → nothing). All forwarding keys on `chat.id`.

## Locked requirements (user)
- Route = (source_chat_id, **source_thread_id**) → (dest_chat_id, **dest_thread_id**).
- Bidirectional **bridge at topic level** (swap chat AND thread on the reverse route).
- Backward compatible: existing routes (no thread ids) = whole group → General.

## Current pipeline (files + roles)

### Data model — `webapp/app/models.py`
- `Route(id, bot_id, source_chat_id, dest_chat_id, enabled, created_at)`
  → ADD `source_thread_id: int | None`, `dest_thread_id: int | None` (nullable, additive).
- `ForwardJob(... dest_chat_id, kind, from_chat_id, message_id, text, entities_json,
  caption, caption_entities_json ...)`
  → ADD `dest_thread_id: int | None` (carried to copy_message/send_message).

### Decision layer (pure) — `webapp/app/forwarding.py`
- `decide_action(update, telegram_bot_id)` → `Action(kind, source_chat_id, message_id,
  sender_username)`. ADD `source_thread_id` (from msg; see researchers for exact field).
- `select_destinations(routes, source_chat_id)` → list of dest ids.
  → REWORK: must match BOTH chat and thread. Return (dest_chat_id, dest_thread_id) pairs.
  Match rule (proposed): route matches when `route.source_chat_id == source AND
  (route.source_thread_id == msg_thread OR route.source_thread_id IS NULL)`.
  (NULL source route = whole group incl. all topics; a topic-specific route only that topic.)
- `build_jobs(...)` creates jobs per dest → must stamp `dest_thread_id` on each job
  (`_copy_job`, `_text_job`, `_copy_caption_job`, `build_labeled_jobs`).
- `chatid` / `start` actions: the `/chatid` reply job must set `dest_thread_id = source_thread_id`
  so the reply lands in the SAME topic; and the text should include the topic id for config.

### Webhook — `webapp/app/webhook.py`
- Loads routes + allowlist, calls build_jobs. No structural change beyond passing routes with
  the new fields (already loaded via `select(Route)`).

### Worker / send — `webapp/app/queue.py` + `webapp/app/botcache.py`
- `send_job(job)`: `copy_message` / `send_message` → ADD `message_thread_id=job["dest_thread_id"]`
  (when not None). `_job_to_dict` must include `dest_thread_id`.
- Worker orders per `dest_chat_id`. Telegram rate limit is per CHAT (whole supergroup), not per
  topic → keep per-chat queue (ordering still correct). Note only.

### Services — `webapp/app/services.py`
- `add_route(session, bot_id, source, dest, bidirectional)` → extend with
  `source_thread_id`, `dest_thread_id`; reverse route swaps BOTH chat and thread.
  Dedup check must include thread ids.
- `delete_route` unchanged (by id).

### UI — `webapp/app/ui.py` + `templates/bot_detail.html`
- `create_route` form: add optional "topic nguồn" + "topic đích" number inputs.
- Route list per source group: currently groups by `source_chat_id` only. With topics, the
  summary/line should show the topic ids (e.g. `-100… (topic 12) → -100… (topic 5)`).
  `source_groups` grouping may need to key on (chat, thread) OR keep chat and show thread per route.
- Sender allowlist/nickname keyed by `source_chat_id` (GLOBAL_SOURCE) → UNCHANGED (gating is per
  group, not per topic). YAGNI: no per-topic sender lists now.

### Migration — `webapp/app/db.py`
- `_add_missing_columns()` adds the 3 new nullable columns automatically. No data backfill
  (existing routes: thread ids NULL = whole group / General → current behavior preserved).

### Tests — `webapp/tests/`
- `test_forwarding.py` (decide_action/select_destinations/build_jobs) — most changes here:
  thread extraction, match precedence (topic-specific vs NULL whole-group), dest_thread_id on jobs.
- `test_services.py` — add_route with thread ids + bidirectional swap.
- `test_webhook_query.py` / worker — dest_thread_id passthrough (assert on ForwardJob rows).
- New: `/chatid` returns topic id + reply into same topic.

## Open questions for design (resolve in research/plan)
- Exact incoming field(s): `message.message_thread_id` + `is_topic_message`? General topic id?
  Do non-forum replies carry message_thread_id (false positives)? → researcher-01.
- Send side: PTB `copy_message`/`send_message` `message_thread_id` support + error when the chat
  isn't a forum / topic missing (permanent vs transient?). → researcher-02.
- Match precedence when BOTH a NULL-source route and a topic route exist (double forward?).
- `/chatid` UX: print `chat_id` + `message_thread_id` only when in a topic.
