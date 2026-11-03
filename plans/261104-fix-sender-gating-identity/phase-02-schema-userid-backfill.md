# Phase 02 — Schema: telegram_user_id on the allowlist + backfill

## Context links
- Parent: [plan.md](./plan.md) · Depends on: Phase 01 (intent = specific people, or hardening) · Research: [research/researcher-02-sqlite-backfill.md](./research/researcher-02-sqlite-backfill.md)

## Overview
- Date: 2026-11-04
- Description: Give each allowlist entry a stable identity. Add a nullable `telegram_user_id` to `AllowedSender`; backfill it from `SenderProfile` (which already captures user_id per sender) by matching username. This is the data foundation for user_id gating (Phase 03).
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- `SenderProfile(bot_id, telegram_user_id, first_name, username)` already exists for everyone who has sent a message — [models.py:122-141](../../webapp/app/models.py#L122-L141). It is the backfill source of truth.
- `_add_missing_columns()` auto-adds any new **nullable** model field via `ALTER TABLE ADD COLUMN` on startup, idempotently — [db.py:47-67](../../webapp/app/db.py#L47-L67). So just adding the field to the model migrates it; no manual DDL.
- Adding nullable `INTEGER` is instant + safe in SQLite; INTEGER is 64-bit signed (fits Telegram user_id). (researcher-02)

## Requirements
- `AllowedSender.telegram_user_id: int | None = None` field added.
- One-time idempotent backfill: set `telegram_user_id` from `SenderProfile` where `allowedsender.username == senderprofile.username` (same bot), only when currently NULL and the profile username is non-null and maps to exactly one user_id.

## Architecture
`models.py` — add to AllowedSender:
```python
telegram_user_id: int | None = Field(default=None, index=True)
```
`db.py` — new idempotent migration, called from `create_db_and_tables()` AFTER `_add_missing_columns()`:
```python
def _backfill_allowed_sender_user_ids() -> None:
    """Link allowlist rows to a stable user_id using captured SenderProfiles.
    Conservative: only username-matched, single-match, currently-NULL rows."""
    insp = inspect(engine)
    if not (insp.has_table("allowedsender") and insp.has_table("senderprofile")):
        return
    with engine.begin() as conn:
        conn.exec_driver_sql("""
            UPDATE allowedsender AS a
               SET telegram_user_id = (
                   SELECT p.telegram_user_id FROM senderprofile p
                    WHERE p.bot_id = a.bot_id AND p.username = a.username
                      AND p.username IS NOT NULL
               )
             WHERE a.telegram_user_id IS NULL
               AND a.username IS NOT NULL
               AND (SELECT COUNT(*) FROM senderprofile p
                     WHERE p.bot_id = a.bot_id AND p.username = a.username
                       AND p.username IS NOT NULL) = 1
        """)
```
(Correlated subquery form → works on all SQLite versions; the `COUNT(*)=1` guard avoids ambiguous multi-match; `IS NULL` guard makes it idempotent — researcher-02.)

## Related code files
- `webapp/app/models.py` (AllowedSender field), `webapp/app/db.py` (`create_db_and_tables` + new `_backfill_allowed_sender_user_ids`).

## Implementation Steps
1. Add the field to `AllowedSender`. 2. Add `_backfill_allowed_sender_user_ids()` and call it in `create_db_and_tables()`. 3. Run app locally against a copy to confirm column added + backfill no-ops on 2nd run.

## Todo list
- [ ] `telegram_user_id` field on AllowedSender
- [ ] `_add_missing_columns` auto-adds it (verify via pragma table_info)
- [ ] backfill migration added + wired + idempotent
- [ ] 158 existing tests still pass

## Success Criteria
- Column exists; existing username-matched senders get their `telegram_user_id` populated from SenderProfile; re-running startup changes nothing.

## Risk Assessment
- Low. Purely additive. Backfill is conservative (single-match, non-null username). Rows with no captured profile stay NULL (handled by username fallback in Phase 03).

## Security Considerations
- No new PII surface (user_id already stored in SenderProfile). No secrets touched.

## Next steps
Phase 03: use the column in the gate.
