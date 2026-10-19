# Phase 01 — Model + migration (topic columns)

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Research: [researcher-01-incoming-topics.md](./research/researcher-01-incoming-topics.md)

## Overview
- Date: 2026-10-19
- Description: Add nullable topic columns to Route and ForwardJob so routes can be topic-scoped and jobs can carry a target topic. Additive only; no behavior change yet.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `None` = whole group / General (backward compatible: existing rows stay NULL).
- Columns are nullable → `_add_missing_columns()` adds them to existing tables without rebuild.

## Requirements
- `Route.source_thread_id: int | None`, `Route.dest_thread_id: int | None`.
- `ForwardJob.dest_thread_id: int | None`.
- Existing 123 tests still pass (no logic change this phase).

## Architecture
```python
# models.py
class Route(SQLModel, table=True):
    # ...existing...
    source_thread_id: int | None = Field(default=None, index=True)
    dest_thread_id: int | None = Field(default=None)

class ForwardJob(SQLModel, table=True):
    # ...existing...
    dest_thread_id: int | None = None
```
Migration: `_add_missing_columns()` (db.py) auto-adds the three nullable columns on startup.
No index strictly required; `source_thread_id` indexed to help match queries (routes are few per
bot, so optional — keep index on source_thread_id only).

## Related code files
- `webapp/app/models.py` — Route + ForwardJob fields.
- `webapp/app/db.py` — no new code (existing additive migration covers it).

## Implementation Steps
1. Add the three fields.
2. Start app / run a scratch `create_db_and_tables()`; verify columns exist on `route` + `forwardjob`.
3. `pytest` — all green (unchanged behavior).

## Todo list
- [ ] Route.source_thread_id / dest_thread_id
- [ ] ForwardJob.dest_thread_id
- [ ] verify migration adds columns

## Success Criteria
- `PRAGMA table_info(route)` shows source_thread_id + dest_thread_id; `forwardjob` shows dest_thread_id.
- Suite green.

## Risk Assessment
- Very low. Pure additive schema.

## Security Considerations
- None (no auth/tenant surface touched).

## Next steps
Phase 02 uses these in the pure decision layer.
