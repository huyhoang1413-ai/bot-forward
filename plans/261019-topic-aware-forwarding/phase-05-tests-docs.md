# Phase 05 — End-to-end tests + docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..04
- Project rule: real DB, NO mocks.

## Overview
- Date: 2026-10-19
- Description: Prove topic routing end-to-end (webhook → ForwardJob with the right dest_thread_id), backward compatibility for non-topic groups, bidirectional swap, service-message skip; update README + roadmap + known limits.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- The pure decision layer carries most of the logic → cover it hardest in test_forwarding.
- Webhook integration test asserts real ForwardJob rows (no network) — same pattern as
  test_webhook_query.py.

## Requirements
- Full suite green. New topic behavior covered; non-topic behavior unchanged.

## Architecture / Test matrix
`test_forwarding.py` (extend):
- `_topic_id`: is_topic_message True + thread → id; thread without is_topic_message → None; neither → None.
- service message (forum_topic_created) → build_jobs == [].
- select_destinations: topic route matches only its topic; NULL route matches any topic + None.
- build_jobs stamps dest_thread_id on copy/text/copy_caption/labeled jobs.
- /chatid in a topic → reply job dest_thread_id == source thread, text contains the topic id.

`test_services.py` (extend):
- add_route with source/dest thread; bidirectional → 2 rows with chat+thread swapped; dedup.

`test_webhook_topic.py` (new, real DB, like test_webhook_query):
- Seed bot + a topic route (source chat X thread 7 → dest Y thread 3) + a whole-group route.
- POST /webhook with a topic-7 message → ForwardJob to Y with dest_thread_id=3 (and the
  whole-group route's job too). A topic-9 message → only the whole-group route fires.
- A non-topic (plain supergroup) message → unchanged.

`test_queue.py` / job-dict (extend): `_job_to_dict` includes dest_thread_id.

`test_ui` (extend/new): create_route with topic fields → rows created; blank → NULL.

Update any existing `select_destinations(...)` test calls to the new signature.

## Related code files
- `webapp/tests/test_forwarding.py`, `test_services.py`, `test_queue.py`, UI tests (update)
- new: `webapp/tests/test_webhook_topic.py`
- `webapp/README.md`, `docs/project-roadmap.md`

## Implementation Steps
1. Update forwarding tests (new select_destinations signature + topic cases).
2. Add webhook topic integration test.
3. Extend services + queue + UI tests.
4. README "Forward theo topic" section + roadmap bullet + known limitation (General vs whole-group).
5. `pytest -q` green.

## Todo list
- [ ] forwarding topic unit tests
- [ ] webhook topic integration test
- [ ] services/queue/UI test updates
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green.
- A topic-7 message lands as a job to the right dest topic; topic-9 doesn't match the topic-7 route.
- Non-forum + existing routes behave exactly as before (regression anchor).

## Risk Assessment
- Low (tests/docs). Main risk: forgetting to update every `select_destinations` call site/test.

## Security Considerations
- Confirm team isolation still applies to topic routes (they're normal /bots/{id} routes).

## Next steps
Deploy: `git pull && docker compose up -d --build`. Users run `/chatid` in each topic to get ids,
then create topic routes.
