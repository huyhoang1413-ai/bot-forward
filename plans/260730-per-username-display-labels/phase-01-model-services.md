# Phase 01 — Data Model + Services + Webhook Wiring

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: existing `webapp/` (models, services, webhook)
- Research: [researcher-02](research/researcher-02-label-design.md) (schema, scope, validation)
- Docs: SQLModel https://sqlmodel.tiangolo.com/

## Overview
- **Date**: 2026-07-30
- **Description**: Add the `SenderLabel` table (per-bot username → label), CRUD services, cascade on bot delete, and load a `label_map` in the webhook to pass into forwarding.
- **Priority**: High (data layer for the feature)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Labels are **independent of the allowlist** → own table. Keyed by `(bot_id, username)` — a person's name is the same across all the bot's groups (covers both bridge sides automatically). Per-bot, not per-source-group.
- Username normalized with the existing `normalize_username` (lowercase, strip `@`) so it matches the sender extracted in `decide_action`.
- Empty/blank label = no row = forward normally.
- `label_map: dict[str, str]` (username → label) is small; load all rows for the bot per webhook call (like `allowed_map`).

## Requirements
- `models.SenderLabel`: `id, bot_id (index), username (lowercased), label, created_at`; `UNIQUE(bot_id, username)`.
- `services.set_label(session, bot_id, username, label)`: normalize username; validate label; upsert (update if exists, else insert); empty label → delete the row.
- `services.delete_label(session, label_id, bot_id)`: scoped delete (IDOR-safe).
- `remove_bot`: cascade-delete `SenderLabel` rows.
- `forwarding.is_valid_label(label)`: ≤32 chars, printable, no `[` `]` or newline; trims whitespace.
- `webhook`: build `label_map` from `SenderLabel` for the bot and pass to `build_jobs` (Phase 02 consumes it).

## Architecture
```
webapp/app/
├── models.py     # + SenderLabel
├── services.py   # set_label / delete_label ; cascade in remove_bot
├── forwarding.py # + is_valid_label (validation helper)
└── webhook.py    # load label_map -> build_jobs(..., label_map=...)
```
Model:
```python
class SenderLabel(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    username: str            # normalized
    label: str
    created_at: datetime = Field(default_factory=_now)
    __table_args__ = (UniqueConstraint("bot_id", "username", name="uq_sender_label"),)
```
Webhook:
```python
label_map = {r.username: r.label
             for r in session.exec(select(SenderLabel).where(SenderLabel.bot_id == bot_id))}
jobs = build_jobs(update, bot_row.telegram_bot_id, routes, bot_id, allowed_map, label_map)
```

## Related code files
- `webapp/app/models.py`, `services.py`, `forwarding.py`, `webhook.py` (edit)
- Tests: `webapp/tests/test_services.py` (extend)

## Implementation Steps
1. Add `SenderLabel` model (auto-created by `create_db_and_tables`).
2. `forwarding.is_valid_label` (pure validation).
3. `services.set_label` (normalize + validate + upsert + empty→delete) and `delete_label` (scoped).
4. Cascade-delete labels in `remove_bot`.
5. Webhook: load `label_map`, pass to `build_jobs` (signature extended in Phase 02; add param now with default `None`).
6. Tests: set/update/delete label, normalization, empty-label removes row, cascade, validation.

## Todo list
- [ ] SenderLabel model
- [ ] is_valid_label
- [ ] set_label / delete_label services
- [ ] cascade in remove_bot
- [ ] webhook loads label_map
- [ ] services tests green

## Success Criteria
- Setting a label for a username stores one normalized row; re-setting updates it; blank label deletes it.
- Deleting a bot removes its labels.
- Invalid labels rejected by `is_valid_label`.

## Risk Assessment
- **Low**: additive table + CRUD. Ensure username normalization matches sender extraction (reuse `normalize_username`).

## Security Considerations
- All mutations behind admin auth (Phase 03 routes). Validate label (no control chars) to avoid odd output. Scoped deletes (IDOR-safe).

## Next steps
Proceed to [Phase 02](phase-02-labeled-forwarding.md) — apply labels in the forwarding pipeline.
