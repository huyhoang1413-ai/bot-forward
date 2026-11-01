# Phase 04 — Retention (3-day prune)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-03

## Overview
- Date: 2026-11-01
- Description: Periodically delete MessageMap rows older than 3 days so the table stays bounded. Off the hot path.
- Priority: Medium
- Implementation status: Not started
- Review status: Pending

## Key Insights
- One map row per delivered message → unbounded without pruning. 3-day window keeps replies-to-recent
  working while bounding size. Prune on a timer in the worker dispatcher, not per message.

## Requirements
- A prune that runs ~every 30-60 min and on startup: `DELETE FROM messagemap WHERE created_at < now-3d`.

## Architecture
```python
# queue.Worker.run() dispatcher loop — throttle prune by a timestamp counter (no Date.now in pure
# code; worker may use real time here since it's runtime, not the pure layer)
RETENTION = timedelta(days=3)
# every N dispatcher ticks (e.g. 3600s / poll) OR track last_prune:
def _prune_message_map(self):
    cutoff = _now_naive() - RETENTION
    with Session(self._engine) as s:
        s.exec(delete(MessageMap).where(MessageMap.created_at < cutoff)); s.commit()
```
Call once at worker start, then every ~30-60 min (compare a monotonically increasing tick or a
stored last-prune time). Uses `ix_msgmap_created`.

## Related code files
- `webapp/app/queue.py` — prune method + schedule in `run()`.
- `webapp/app/db.py` — optional standalone `prune_message_map()` for a test to call.

## Implementation Steps
1. Add prune (bulk delete by created_at) + schedule in the dispatcher.
2. Test: seed old + new rows → prune removes only old.

## Todo list
- [ ] prune method (bulk delete < now-3d)
- [ ] schedule in worker (startup + periodic)
- [ ] prune test

## Success Criteria
- Rows older than 3 days are removed; recent rows kept; runs without blocking sends.

## Risk Assessment
- Low. Bulk delete on an indexed column. Keep interval coarse (30-60 min) to avoid churn.

## Security Considerations
- None.

## Next steps
Phase 05: tests + docs.
