# Phase 03 — Send path (deliver into the topic)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02
- Research: [researcher-02-sending-topics.md](./research/researcher-02-sending-topics.md)

## Overview
- Date: 2026-10-19
- Description: Carry ForwardJob.dest_thread_id to Telegram via `message_thread_id` on copy_message / send_message. None → General. No change to error handling or worker ordering.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- PTB ≥21 `copy_message`/`send_message` accept `message_thread_id: int | None`; None → General.
- Topic errors are `BadRequest`/`Forbidden` → botcache ALREADY raises `PermanentSendError`
  (fail-fast, won't block the chat queue). No new error code.
- Rate limit is per-chat → worker's per-`dest_chat_id` queue stays. No change.

## Requirements
- `_job_to_dict` includes `dest_thread_id`.
- `send_job` passes `message_thread_id=job["dest_thread_id"]` on both `send_message`
  (kind "text") and `copy_message` (kinds "copy", "copy_caption").

## Architecture
```python
# queue.py _job_to_dict
"dest_thread_id": job.dest_thread_id,

# botcache.py send_job
mt = job.get("dest_thread_id")
if kind == "text":
    await bot.send_message(chat_id=job["dest_chat_id"], text=job["text"],
                           entities=..., message_thread_id=mt)
elif kind == "copy_caption":
    await bot.copy_message(chat_id=..., from_chat_id=..., message_id=...,
                           caption=..., caption_entities=..., message_thread_id=mt)
else:  # copy
    await bot.copy_message(chat_id=..., from_chat_id=..., message_id=...,
                           message_thread_id=mt)
```
`mt=None` is passed through harmlessly (General / normal group). BadRequest/Forbidden still
caught by the existing `except (BadRequest, Forbidden)` → `PermanentSendError`.

## Related code files
- `webapp/app/queue.py` — `_job_to_dict` adds dest_thread_id.
- `webapp/app/botcache.py` — `send_job` passes message_thread_id on all three send calls.

## Implementation Steps
1. Add dest_thread_id to `_job_to_dict`.
2. Add `message_thread_id=` to the three send calls in send_job.
3. Tests: assert ForwardJob rows carry dest_thread_id (worker/webhook); a unit test that
   send_job forwards the thread id (can assert via a fake send_fn capturing kwargs — but project
   bans mocks; instead assert the job dict shape + that _job_to_dict includes it).

## Todo list
- [ ] _job_to_dict dest_thread_id
- [ ] send_job message_thread_id on text/copy/copy_caption
- [ ] passthrough test (job dict shape)

## Success Criteria
- A job with dest_thread_id=5 results in a copy_message/send_message carrying message_thread_id=5;
  dest_thread_id=None sends normally (verified via job-dict + integration job rows).
- Existing delivery for non-topic jobs unchanged.

## Risk Assessment
- Low. Additive kwarg. No-mock rule → verify at the job-dict + DB-row level (send itself hits the
  network, already untested by design).

## Security Considerations
- None new.

## Next steps
Phase 04 exposes topic config in services + UI.
