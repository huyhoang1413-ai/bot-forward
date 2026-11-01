# Phase 05 — Tests + docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..04
- Project rule: real DB, NO mocks (Telegram network not called in tests — assert ForwardJob/MessageMap state + a fake send_fn for the worker).

## Overview
- Date: 2026-11-01
- Description: Cover reply extraction, job stamping, send-time resolution + capture, quote fallback, ordering, and pruning. Update README + roadmap.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Pure layer (decide_action/build_jobs) tested directly. The worker's resolve+capture tested with a
  fake `send_fn` that returns incrementing message ids (no network), asserting MessageMap + reply_to.

## Requirements
- Full suite green; reply link + fallback + capture + ordering + prune all asserted.

## Architecture / Test matrix
`test_forwarding.py` (extend):
- decide_action: reply update → `reply_to_source_message_id` + clamped `reply_quote`; non-reply → None.
- sanitize_quote: clamp length, strip `\r\n`, keep unicode.
- build_jobs: every job carries origin_chat_id/origin_message_id + reply fields.

`test_queue.py` / `test_worker.py` (extend) with a fake send_fn returning ids:
- Deliver original (stores MessageMap) then its reply → reply job resolved to the original's dest id
  (reply_to_message_id passed to send_fn) BEFORE delivery (per-dest ordering).
- No map (reply to an unforwarded msg) → send_fn receives reply_to=None + the quote fallback.
- Capture: after delivering a message, a MessageMap row exists (bot/dest/source/src_msg → dest_msg).

`test_webhook_reply.py` (new, real DB, fake worker not run) OR extend send tests:
- Post original then reply via `/webhook/{id}`; run a minimal deliver loop with a fake send_fn;
  assert the reply's delivered job referenced the original's dest id.

`test_retention.py` (new): seed MessageMap old (>3d) + new → prune removes only old.

Update: `_job_to_dict` field additions; any worker test asserting the old send_fn signature
(now returns an id).

## Related code files
- `webapp/tests/test_forwarding.py`, `test_worker.py`/`test_queue.py` (extend)
- new: `test_webhook_reply.py` (or fold in), `test_retention.py`
- `webapp/README.md`, `docs/project-roadmap.md`

## Implementation Steps
1. Pure reply/quote tests.
2. Worker resolve+capture+fallback tests (fake send_fn returning ids).
3. Retention prune test.
4. README "Forward giữ ngữ cảnh trả lời" section + roadmap bullet.
5. `pytest -q` green.

## Todo list
- [ ] forwarding reply/quote/stamp tests
- [ ] worker resolve + capture + fallback tests
- [ ] retention prune test
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green.
- A test proves: original delivered → reply delivered as a reply to the correct dest message; and
  an unmapped reply degrades to the quote fallback; map pruned after 3 days.

## Risk Assessment
- Low (tests/docs). Ensure the fake send_fn mirrors the real return contract (int message id).

## Security Considerations
- Quote sanitization asserted (untrusted content safety).

## Next steps
Deploy: `git pull && docker compose up -d --build` (additive migration). Replies now keep context.
