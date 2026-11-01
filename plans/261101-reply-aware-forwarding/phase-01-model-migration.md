# Phase 01 — Model + migration

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Research: [researcher-02-mapping-store.md](./research/researcher-02-mapping-store.md)

## Overview
- Date: 2026-11-01
- Description: Add the `MessageMap` table and the `ForwardJob` fields needed to map source→dest message ids and carry reply context. Additive only; no behavior change yet.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Map keyed (bot_id, dest_chat_id, source_chat_id, source_message_id) → dest_message_id; lookup at
  send time. created_at index for 3-day pruning. No UNIQUE (dupes harmless; prune bounds growth).
- Jobs must carry the SOURCE identity for ALL kinds (text/copy/copy_caption) so the map can be
  stored after any send, plus the replied-to source id + a prebuilt quote for the fallback.

## Requirements
- `MessageMap(id, bot_id, dest_chat_id, source_chat_id, source_message_id, dest_message_id, created_at)`.
- `ForwardJob` + `origin_chat_id`, `origin_message_id`, `reply_to_source_message_id`, `reply_quote`
  (all nullable).
- Existing 150 tests still pass.

## Architecture
```python
# models.py
class MessageMap(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    dest_chat_id: int
    source_chat_id: int
    source_message_id: int
    dest_message_id: int
    created_at: datetime = Field(default_factory=_now_naive)
    __table_args__ = (
        Index("ix_msgmap_lookup", "bot_id", "dest_chat_id", "source_chat_id", "source_message_id"),
        Index("ix_msgmap_created", "created_at"),
    )

class ForwardJob(SQLModel, table=True):
    # ...existing...
    origin_chat_id: int | None = None       # SOURCE chat of the forwarded msg (all kinds)
    origin_message_id: int | None = None    # SOURCE message id (for storing the map after send)
    reply_to_source_message_id: int | None = None  # the replied-to msg id in the source chat
    reply_quote: str | None = None          # prebuilt "↳ name: snippet" for the no-map fallback
```
Migration: `MessageMap` via `create_all()`; 4 `ForwardJob` cols via `_add_missing_columns` (nullable).

## Related code files
- `webapp/app/models.py` — MessageMap + ForwardJob fields.
- `webapp/app/db.py` — (prune helper added in phase-04).

## Implementation Steps
1. Add MessageMap + indexes.
2. Add the 4 ForwardJob columns.
3. Scratch `create_db_and_tables()`; verify table + columns on an existing DB.
4. `pytest` green.

## Todo list
- [ ] MessageMap model + indexes
- [ ] ForwardJob reply/origin columns
- [ ] migration verified on existing DB

## Success Criteria
- `messagemap` table + new `forwardjob` columns present after migrating an existing DB.

## Risk Assessment
- Low. Additive. created_at uses `_now_naive` (consistent with ForwardJob scheduling).

## Security Considerations
- Stores message ids only (no content except the short quote snippet). Per-bot scoped.

## Next steps
Phase 02 extracts reply info and stamps jobs.
