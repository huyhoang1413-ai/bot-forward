# Phase 01 — Model + migration

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Research: [researcher-02-capture-storage.md](./research/researcher-02-capture-storage.md)

## Overview
- Date: 2026-10-20
- Description: Add the per-bot `auto_nick` flag and the `SenderProfile` capture table. Additive only; no behavior change yet.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `SenderProfile` is keyed by `(bot_id, telegram_user_id)` — covers username-less users.
- `first_name` captured once; `label_override` admin-set; both nullable-friendly for additive migration.

## Requirements
- `Bot.auto_nick: bool = False`.
- `SenderProfile(id, bot_id, telegram_user_id, first_name, label_override, username, captured_at)`
  with UNIQUE(bot_id, telegram_user_id).
- Existing 137 tests still pass.

## Architecture
```python
# models.py
class Bot(SQLModel, table=True):
    # ...existing...
    auto_nick: bool = Field(default=False)

class SenderProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    telegram_user_id: int = Field(index=True)
    first_name: str                       # captured once (never overwritten)
    label_override: str | None = None     # admin edit; wins over first_name
    username: str | None = None           # may refresh on later sightings
    captured_at: datetime = Field(default_factory=_now)
    __table_args__ = (
        UniqueConstraint("bot_id", "telegram_user_id", name="uq_sender_profile"),
        Index("ix_sender_profile_bot_first", "bot_id", "first_name"),  # UI list/search
    )
```
Migration: `_add_missing_columns()` adds `bot.auto_nick` (bool has a default → OK). `SenderProfile`
created by `create_all()`. No data backfill.
Note: `auto_nick` is a NOT NULL bool with default False — ensure the additive migration supplies a
server default (or add it as nullable then default). If `_add_missing_columns` can't add NOT NULL,
declare `auto_nick: bool | None = Field(default=False)` OR add with server_default="0".

## Related code files
- `webapp/app/models.py` — Bot.auto_nick + SenderProfile.
- `webapp/app/db.py` — verify `_add_missing_columns` adds auto_nick (bool default). If it skips
  non-nullable-no-server-default cols, add `sa_column_kwargs={"server_default": "0"}` to the field.

## Implementation Steps
1. Add `Bot.auto_nick` (with server_default so migration can add it to existing `bot` table).
2. Add `SenderProfile`.
3. Run scratch `create_db_and_tables()`; verify `bot.auto_nick` column + `senderprofile` table.
4. `pytest` green.

## Todo list
- [ ] Bot.auto_nick (migration-safe default)
- [ ] SenderProfile model + constraints/index
- [ ] verify migration on an existing DB

## Success Criteria
- `bot` has `auto_nick` (default 0) after migrating an existing DB; `senderprofile` table exists.
- Suite green.

## Risk Assessment
- Low-medium. The ONLY subtlety: adding a NOT NULL bool to an existing table — use a server_default
  ("0") so `ALTER TABLE ADD COLUMN` succeeds on the live prod DB.

## Security Considerations
- None (no auth/tenant surface). SenderProfile is per-bot; UI access already gated by bot access.

## Next steps
Phase 02 captures names into SenderProfile.
