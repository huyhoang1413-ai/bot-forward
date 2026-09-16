# Phase 01 — Model + Migration

## Context links
- Parent: [plan.md](./plan.md)
- Research: [researcher-01-data-model.md](./research/researcher-01-data-model.md)
- Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Depends on: none (foundation phase)

## Overview
- Date: 2026-09-16
- Description: Add `SenderGroupAssignment` junction table + idempotent backfill migration so the global allowlist gains per-group scoping without behavior change.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `AllowedSender` stays a GLOBAL registry (one row per `(bot_id, username)`, `source_chat_id` fixed to `GLOBAL_SOURCE=0`). Do NOT alter its constraint (migrations are additive-only).
- New scoping lives entirely in a separate junction table → clean, FK-backed, no JSON.
- Backfill assigns every existing sender to every existing source group of its bot → identical forwarding after deploy.

## Requirements
- New table `SenderGroupAssignment` created by `SQLModel.metadata.create_all()`.
- One-time idempotent migration assigning existing senders to all their bot's source groups.
- No destructive DDL. Existing 75 tests unaffected by the schema addition.

## Architecture
```python
# models.py — add below AllowedSender
class SenderGroupAssignment(SQLModel, table=True):
    """Which global AllowedSender applies to which source group (many-to-many)."""
    id: int | None = Field(default=None, primary_key=True)
    allowed_sender_id: int = Field(foreign_key="allowedsender.id", index=True)
    source_chat_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)

    __table_args__ = (
        UniqueConstraint("allowed_sender_id", "source_chat_id", name="uq_sender_group_assign"),
        Index("ix_group_sender", "source_chat_id", "allowed_sender_id"),
    )
```
`Index` import: `from sqlalchemy import Index, UniqueConstraint`.

Migration (db.py), called from `create_db_and_tables()` AFTER `_collapse_allowed_senders_to_global()`:
```python
def _backfill_group_sender_assignments() -> None:
    """One-time idempotent: assign every existing global sender to every distinct
    source group of its bot, preserving today's 'applies to all groups' behavior.
    No-op once assignments already exist for a (sender, group) pair."""
    from app.models import AllowedSender, Route, SenderGroupAssignment
    if not inspect(engine).has_table("sendergroupassignment"):
        return
    with Session(engine) as s:
        senders = s.exec(select(AllowedSender)).all()
        if not senders:
            return
        # existing pairs -> skip set
        existing = {
            (a.allowed_sender_id, a.source_chat_id)
            for a in s.exec(select(SenderGroupAssignment)).all()
        }
        # bot_id -> distinct source groups
        routes = s.exec(select(Route)).all()
        groups_by_bot: dict[int, set[int]] = {}
        for r in routes:
            groups_by_bot.setdefault(r.bot_id, set()).add(r.source_chat_id)
        made = False
        for snd in senders:
            for src in groups_by_bot.get(snd.bot_id, ()):  # sender has no groups -> nothing
                if (snd.id, src) in existing:
                    continue
                s.add(SenderGroupAssignment(allowed_sender_id=snd.id, source_chat_id=src))
                made = True
        if made:
            s.commit()
```
Idempotency: re-running skips pairs already present. A sender whose bot has no routes gets no assignments (correct — nothing to forward yet).

## Related code files
- `webapp/app/models.py` — add model + `Index` import.
- `webapp/app/db.py` — add `_backfill_group_sender_assignments()`, call in `create_db_and_tables()`.

## Implementation Steps
1. Add `Index` to the sqlalchemy import in models.py.
2. Add `SenderGroupAssignment` class after `AllowedSender`.
3. In db.py add the backfill fn; call it after the collapse migration.
4. Restart app locally; verify table exists and rows backfilled for bot 1 (2 senders × its source groups).

## Todo list
- [ ] models: `SenderGroupAssignment` + constraint + index
- [ ] db: backfill fn + wiring
- [ ] manual verify on real DB (bot 1)

## Success Criteria
- `sendergroupassignment` table exists after startup.
- For current DB (2 senders, source groups -5402649159 & -5416079023): backfill yields 2×2 = 4 assignment rows.
- Re-running startup adds no duplicate rows (idempotent).

## Risk Assessment
- Low. Additive table + additive data. Worst case backfill no-op.
- Edge: sender rows whose `bot_id` has zero routes → no assignments (acceptable; they had nowhere to forward anyway).

## Security Considerations
- No user input in this phase. FK enforces sender existence. No IDOR surface (internal migration).

## Next steps
Phase 02 consumes the new table in the forwarding hot path.
