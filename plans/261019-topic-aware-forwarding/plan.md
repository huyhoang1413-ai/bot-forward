# Plan: Topic-aware forwarding (per source/dest topic pair)

Date: 2026-10-19 · Status: Ready for review · Priority: Medium-High

## Goal
Forward Telegram **forum topics** precisely: a route maps (source group + source topic) →
(dest group + dest topic). **Bidirectional bridge at topic level**. Backward compatible:
existing routes (no topic ids) = whole group → General.

## Locked design (from research 01 incoming + 02 sending)
- **Topic key (incoming)**: `source_thread_id = msg.message_thread_id if msg.is_topic_message
  else None`. General / non-forum = `None`.
- **Route model**: add `Route.source_thread_id`, `Route.dest_thread_id` (nullable, additive).
  `ForwardJob.dest_thread_id` (nullable) carries the target topic to the send call.
- **Match rule**: a route matches a message when `route.source_chat_id == src AND
  (route.source_thread_id IS NULL OR route.source_thread_id == src_thread)`. NULL-source route =
  whole group (all topics incl. General); a topic-specific route = only that topic.
- **Send**: `copy_message(..., message_thread_id=dest_thread_id)` / `send_message(..., message_thread_id=...)`.
  `None` → General. Topic errors (`BadRequest`/`Forbidden`) are ALREADY permanent in botcache → fail-fast.
- **Rate limit** per-chat → worker keeps per-`dest_chat_id` queue (no change).
- **Service messages** (forum_topic_created/edited/closed/reopened, general_forum_topic_hidden/
  unhidden) → skipped (not forwarded).
- **/chatid** in a topic → reply shows `chat_id` + `message_thread_id`, and the reply is sent INTO
  the same topic (dest_thread_id = source_thread_id).
- **Senders/nickname** stay per-group (keyed by source_chat_id) — unchanged (YAGNI, not per-topic).

## Phases (each independently testable)
1. **phase-01-model-migration.md** — Route.source_thread_id/dest_thread_id + ForwardJob.dest_thread_id; additive migration.
2. **phase-02-decision-layer.md** — decide_action topic extraction + service-msg skip; select_destinations → (chat,thread) pairs; build_jobs stamps dest_thread_id; /chatid topic reply. (pure tests)
3. **phase-03-send-path.md** — ForwardJob field through _job_to_dict → send_job `message_thread_id` on copy/send.
4. **phase-04-services-ui.md** — add_route(source/dest thread, bidirectional swaps both); create_route form + route list shows topic ids.
5. **phase-05-tests-docs.md** — end-to-end (topic message → correct dest_thread_id job; backward-compat non-topic); README + roadmap + known limits.

## Key files
- `webapp/app/models.py`, `db.py`, `forwarding.py`, `webhook.py`, `queue.py`, `botcache.py`,
  `services.py`, `ui.py`, `templates/bot_detail.html`, `webapp/tests/`.

## Backward-compat / deploy
- Additive migration only; existing routes (thread ids NULL) behave exactly as today.
- Non-forum groups unaffected (topic key always None).

## Open questions / decisions for reviewer
1. **General-only routing**: with `None` = whole-group, a route cannot target *only* General
   distinctly from "whole group". Acceptable (YAGNI)? If needed later, add a sentinel.
2. **Non-forum service messages** (new_chat_members, pinned, etc.) keep current behavior
   (forwarded as "other") — only FORUM topic service messages are skipped. OK?
3. **Topic name display** in UI/`/chatid` (needs an extra API call) — deferred; show numeric id only. OK?
