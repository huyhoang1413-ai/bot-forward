# Phase 01 — Backend: index, single-JOIN webhook, service helpers

## Context links
- Parent: [plan.md](./plan.md)
- Research: [researcher-01-search-pagination.md](./research/researcher-01-search-pagination.md)
- Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Depends on: existing junction feature (commit after 260916 per-group assignment)

## Overview
- Date: 2026-09-16
- Description: Add the search index, collapse the webhook allowlist fetch to one LEFT JOIN, and add reusable service helpers for search/pagination + incremental per-group add/remove. No behavior change.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `create_all()` won't add an index to an existing table, and `COLLATE NOCASE` needs raw DDL → use an additive `CREATE INDEX IF NOT EXISTS` step.
- Webhook currently does 2 queries + a `.in_(1000 ids)` list (near SQLite's 999 param limit). A single LEFT JOIN filtered by `bot_id` removes the IN-list entirely.
- All heavy reads are paginated at the service layer so UI never loads 1000 rows.

## Requirements
- Additive index `ix_allowedsender_bot_username (bot_id, username COLLATE NOCASE)`.
- Webhook builds `label_map`, `allowed_by_source`, `gate_active` from ONE query.
- Service helpers: registry search+paginate; group assigned list; unassigned picker; idempotent add/remove (bot-scoped IDOR).
- Existing 89 tests still pass (forwarding decision tree unchanged).

## Architecture
Index migration (db.py), called from `create_db_and_tables()`:
```python
def _add_search_indexes() -> None:
    if not inspect(engine).has_table("allowedsender"):
        return
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_allowedsender_bot_username "
            "ON allowedsender(bot_id, username COLLATE NOCASE)"
        )
```
Webhook single LEFT JOIN (webhook.py):
```python
rows = session.exec(
    select(AllowedSender, SenderGroupAssignment).join(
        SenderGroupAssignment,
        AllowedSender.id == SenderGroupAssignment.allowed_sender_id,
        isouter=True,
    ).where(AllowedSender.bot_id == bot_id)
).all()
label_map, allowed_by_source = {}, {}
for snd, assign in rows:
    label_map[snd.username] = snd.label
    if assign is not None:
        allowed_by_source.setdefault(assign.source_chat_id, {})[snd.username] = snd.label
gate_active = bool(label_map)
```
Service helpers (services.py) — all `page` 0-based, return `(items, total)`:
```python
PAGE_SIZE = 50

def _norm_q(q): return (q or "").strip().lstrip("@").lower()

def list_senders(session, bot_id, q="", page=0, page_size=PAGE_SIZE):
    base = select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    if q: base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    items = session.exec(base.order_by(AllowedSender.username)
                         .offset(page*page_size).limit(page_size)).all()
    return items, total

def list_group_senders(session, bot_id, source, q="", page=0, page_size=PAGE_SIZE):
    base = select(AllowedSender).join(
        SenderGroupAssignment, AllowedSender.id == SenderGroupAssignment.allowed_sender_id
    ).where(AllowedSender.bot_id == bot_id,
            SenderGroupAssignment.source_chat_id == source)
    if q: base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    ... offset/limit + count ...

def search_unassigned(session, bot_id, source, q="", page=0, page_size=PAGE_SIZE):
    sub = select(SenderGroupAssignment.allowed_sender_id).where(
        SenderGroupAssignment.source_chat_id == source)
    base = select(AllowedSender).where(
        AllowedSender.bot_id == bot_id, ~AllowedSender.id.in_(sub))
    if q: base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    ... offset/limit + count ...

def add_group_sender(session, bot_id, source, sender_id) -> bool:
    snd = session.get(AllowedSender, sender_id)
    if not snd or snd.bot_id != bot_id: return False           # IDOR
    if session.exec(select(Route.source_chat_id).where(
        Route.bot_id==bot_id, Route.source_chat_id==source)).first() is None:
        return False                                           # not a real source
    if not session.exec(select(SenderGroupAssignment).where(
        SenderGroupAssignment.allowed_sender_id==sender_id,
        SenderGroupAssignment.source_chat_id==source)).first():
        session.add(SenderGroupAssignment(allowed_sender_id=sender_id, source_chat_id=source))
        session.commit()
    return True

def remove_group_sender(session, bot_id, source, sender_id) -> None:
    snd = session.get(AllowedSender, sender_id)
    if not snd or snd.bot_id != bot_id: return
    a = session.exec(select(SenderGroupAssignment).where(
        SenderGroupAssignment.allowed_sender_id==sender_id,
        SenderGroupAssignment.source_chat_id==source)).first()
    if a: session.delete(a); session.commit()
```
Keep `set_group_senders` temporarily (retired in phase-03) to avoid breaking tests before UI swaps.

## Related code files
- `webapp/app/db.py` — `_add_search_indexes()` + call.
- `webapp/app/webhook.py` — single LEFT JOIN; keep imports.
- `webapp/app/services.py` — helpers above; import `func` from sqlalchemy.

## Implementation Steps
1. db.py: add index migration + wire after existing migrations.
2. webhook.py: replace 2-query build with single LEFT JOIN.
3. services.py: add 5 helpers + PAGE_SIZE + `_norm_q`.
4. `pytest` — existing green; webhook behavior identical.

## Todo list
- [ ] index migration (CREATE INDEX IF NOT EXISTS, COLLATE NOCASE)
- [ ] webhook single LEFT JOIN
- [ ] service helpers (list/search/add/remove)

## Success Criteria
- Index present after startup (`PRAGMA index_list(allowedsender)`).
- Webhook produces identical `allowed_by_source`/`label_map` with ONE query (assert via a test).
- Helpers return correct paginated slices + totals; add/remove idempotent & bot-scoped.

## Risk Assessment
- Low. Index is additive; JOIN returns same data. `func.count` on subquery — verify SQLModel syntax (`select(func.count()).select_from(base.subquery())`).
- Watch: `startswith` escapes `%`/`_`? SQLAlchemy `.startswith` auto-escapes by default. OK.

## Security Considerations
- IDOR: add/remove verify sender.bot_id == bot_id AND source is a real route source of the bot.
- No raw string interpolation in queries (parameter-bound). Index DDL is static SQL.

## Next steps
Phase 02 builds the registry manager page on these helpers.
