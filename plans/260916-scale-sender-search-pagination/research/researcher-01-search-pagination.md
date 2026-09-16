# Research: Scalable Sender Allowlist Search + Pagination (FastAPI/SQLModel/SQLite)

**Goal:** Optimize 500–1000 sender registry queries (case-insensitive search, per-group assignments) in Telegram forwarding bot.

---

## 1. Search: Prefix vs Substring

**Recommendation: `LIKE 'q%'` (prefix) with `COLLATE NOCASE` index.**

### SQLite LIKE Behavior
- SQLite `LIKE` is **case-insensitive by default on ASCII chars only** (no accents).
- `COLLATE NOCASE` on the index column ensures prefix matching uses the B-tree.
- **Substring `LIKE '%q%'` does NOT use index** (SQLite doesn't plan prefix scan on trailing wildcard); full table scan.

### Schema + Index
```sql
ALTER TABLE allowedsender ADD CONSTRAINT chk_username_lower
  CHECK (username = LOWER(username));

CREATE INDEX ix_allowedsender_bot_username 
  ON allowedsender(bot_id, username COLLATE NOCASE);
```

### SQLAlchemy Query (Prefix)
```python
from sqlalchemy import func
from sqlmodel import select

q = "john"  # user input; app already normalizes to lowercase
stmt = select(AllowedSender).where(
    AllowedSender.bot_id == bot_id,
    AllowedSender.username.startswith(q)  # SQLAlchemy .startswith() → LIKE 'q%'
).limit(50)

senders = session.exec(stmt).all()
```

**Why prefix?** Most UX: user types "joh" → matches "john", "johnson", "johanna". 
Substring = scanning full table; avoid unless client drives it.

### Substring (if needed)
```python
# Anti-pattern: forces full scan
stmt = select(AllowedSender).where(
    AllowedSender.bot_id == bot_id,
    AllowedSender.username.contains(q)
)
```

**Citation:** [SQLite LIKE docs](https://www.sqlite.org/lang_expr.html#like), [SQLAlchemy .startswith()](https://docs.sqlalchemy.org/en/20/core/sqlelement.html#sqlalchemy.sql.expression.ColumnElement.startswith)

---

## 2. Pagination: Offset vs Keyset

**Recommendation: Offset-based `.offset(page * size).limit(size)` for ≤1000 rows.**

### Why Offset
- Simplest UX: `?page=1&page_size=20`.
- Offset O(n) cost is acceptable at 1000 rows; becomes painful at 1M+.
- Keyset (cursor) better for large datasets but adds complexity (encode/decode ID).

### Query
```python
page = 0  # first page
page_size = 20
stmt = select(AllowedSender).where(
    AllowedSender.bot_id == bot_id,
    AllowedSender.username.startswith(q)
).offset(page * page_size).limit(page_size)

senders = session.exec(stmt).all()
total_count = session.exec(
    select(func.count()).select_from(AllowedSender).where(
        AllowedSender.bot_id == bot_id,
        AllowedSender.username.startswith(q)
    )
).scalar()
```

### Query Params
```
GET /bots/{bot_id}/allowed?q=john&page=0&page_size=20
Response: { "items": [...], "total": 342, "page": 0, "page_size": 20 }
```

**Citation:** [SQLAlchemy .offset() / .limit()](https://docs.sqlalchemy.org/en/20/orm/queryguide/select.html#limiting-with-limit-offset)

---

## 3. Per-Group Assigned Senders + Inverse (Add Picker)

### Assigned Senders (List group's senders)
```python
# List senders assigned to source_chat_id
stmt = select(AllowedSender).join(
    SenderGroupAssignment,
    AllowedSender.id == SenderGroupAssignment.allowed_sender_id
).where(
    AllowedSender.bot_id == bot_id,
    SenderGroupAssignment.source_chat_id == source_chat_id,
    AllowedSender.username.startswith(q)
).offset(0).limit(20)

assigned = session.exec(stmt).all()
```

### Inverse: NOT Yet Assigned (Add Picker)
```python
# Senders in bot but NOT assigned to this group
stmt = select(AllowedSender).where(
    AllowedSender.bot_id == bot_id,
    AllowedSender.username.startswith(q),
    ~AllowedSender.id.in_(
        select(SenderGroupAssignment.allowed_sender_id).where(
            SenderGroupAssignment.source_chat_id == source_chat_id
        )
    )
).offset(0).limit(20)

unassigned = session.exec(stmt).all()
```

**Alt (NOT EXISTS)**
```python
# Equivalent, sometimes faster on large subqueries
from sqlalchemy import exists

not_exists = ~exists(
    select(1).select_from(SenderGroupAssignment).where(
        SenderGroupAssignment.allowed_sender_id == AllowedSender.id,
        SenderGroupAssignment.source_chat_id == source_chat_id
    )
)
stmt = select(AllowedSender).where(
    AllowedSender.bot_id == bot_id,
    AllowedSender.username.startswith(q),
    not_exists
).limit(20)
```

---

## 4. Incremental Mutations (Add/Remove without Replace-All)

**Recommendation: Two endpoints per group instead of posting full checklist.**

### Endpoint 1: Add Sender to Group
```python
@router.post("/bots/{bot_id}/groups/{source_chat_id}/senders/{sender_id}")
async def add_group_sender(
    bot_id: int, source_chat_id: int, sender_id: int,
    session: Session = Depends(get_session)
):
    # IDOR guards: verify sender belongs to bot, source is a route source
    sender = session.get(AllowedSender, sender_id)
    if not sender or sender.bot_id != bot_id:
        raise HTTPException(403, "Sender not found")
    
    route = session.exec(
        select(Route).where(
            Route.bot_id == bot_id,
            Route.source_chat_id == source_chat_id
        )
    ).first()
    if not route:
        raise HTTPException(404, "Source not a route source")
    
    # Idempotent: upsert
    assign = session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.allowed_sender_id == sender_id,
            SenderGroupAssignment.source_chat_id == source_chat_id
        )
    ).first()
    if not assign:
        session.add(SenderGroupAssignment(
            allowed_sender_id=sender_id, source_chat_id=source_chat_id
        ))
    session.commit()
    return {"ok": True}
```

### Endpoint 2: Remove Sender from Group
```python
@router.delete("/bots/{bot_id}/groups/{source_chat_id}/senders/{sender_id}")
async def remove_group_sender(
    bot_id: int, source_chat_id: int, sender_id: int,
    session: Session = Depends(get_session)
):
    sender = session.get(AllowedSender, sender_id)
    if not sender or sender.bot_id != bot_id:
        raise HTTPException(403, "Sender not found")
    
    assign = session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.allowed_sender_id == sender_id,
            SenderGroupAssignment.source_chat_id == source_chat_id
        )
    ).first()
    if assign:
        session.delete(assign)
        session.commit()
    return {"ok": True}
```

**Benefits:** Clients post only the changed sender, not the full list. Avoids race conditions.

---

## 5. Webhook Hot Path: 1000 Senders

**Current (2 queries):**
```python
# Q1: all bot senders
senders = session.exec(select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()
by_id = {s.id: s for s in senders}

# Q2: per-source assignments (builds dict)
for a in session.exec(
    select(SenderGroupAssignment).where(
        SenderGroupAssignment.allowed_sender_id.in_(list(by_id.keys()))
    )
).all():
    ...
```

**Problem:** `IN (1,2,3,...,1000)` works but SQLite parameter limit is 999/32766 depending on version. 
At exactly 1000 senders, you're at the edge.

**Recommendation: Single JOIN Query (No IN-list)**
```python
# One query: load only the assignment data for senders we need (filtered by bot_id via FK)
stmt = select(AllowedSender, SenderGroupAssignment).join(
    SenderGroupAssignment,
    AllowedSender.id == SenderGroupAssignment.allowed_sender_id,
    isouter=True  # include senders not yet assigned to any group
).where(
    AllowedSender.bot_id == bot_id
)

rows = session.exec(stmt).all()

# Build maps in memory (1 query, no IN-list)
label_map: dict[str, str | None] = {}
allowed_by_source: dict[int, dict[str, str | None]] = {}
for sender, assignment in rows:
    label_map[sender.username] = sender.label
    if assignment:
        allowed_by_source.setdefault(assignment.source_chat_id, {})[sender.username] = sender.label
```

**SQL:**
```sql
SELECT 
  allowedsender.*, sendergroupassignment.*
FROM allowedsender
LEFT JOIN sendergroupassignment 
  ON allowedsender.id = sendergroupassignment.allowed_sender_id
WHERE allowedsender.bot_id = ?
```

**Index:** `ix_group_sender` (already exists: `source_chat_id, allowed_sender_id`).

**Benefit:** Single DB round-trip, no IN-list, scales to any sender count.

---

## 6. Indexes to Add (Additive)

Current indexes from schema:
- `Bot.telegram_bot_id` (unique)
- `Route.bot_id`
- `Route.source_chat_id`
- `AllowedSender.bot_id`
- `AllowedSender.source_chat_id`
- `SenderGroupAssignment.allowed_sender_id`
- `SenderGroupAssignment.source_chat_id`
- `SenderGroupAssignment.ix_group_sender(source_chat_id, allowed_sender_id)`

**Add (DDL migrations):**
```python
# In models.py __table_args__ or separate migration:

# 1. Composite index for prefix search + pagination
Index("ix_allowedsender_bot_username", 
      "bot_id", "username", 
      info={"sqlite_collate": "NOCASE"})

# 2. Speed up joined queries (select list of senders per group)
Index("ix_sendergroupassignment_source_sender",
      "source_chat_id", "allowed_sender_id")  # Already exists as ix_group_sender

# 3. Speed up unassigned-sender picker (NOT IN subquery)
Index("ix_allowedsender_bot_username_pk",
      "bot_id", "username")  # Or just rely on compound index above
```

**Additive migration (no alter):**
```python
# db.py _add_missing_indexes()
def _add_missing_indexes() -> None:
    """Add missing indexes without dropping tables."""
    insp = inspect(engine)
    with engine.begin() as conn:
        existing_idx = {i['name'] for i in insp.get_indexes(table_name)}
        
        if 'ix_allowedsender_bot_username' not in existing_idx:
            conn.exec_driver_sql(
                "CREATE INDEX ix_allowedsender_bot_username "
                "ON allowedsender(bot_id, username COLLATE NOCASE)"
            )
```

---

## Unresolved Questions

1. **Label search:** Should `label` field also be searchable (case-insensitive)? Current approach only searches `username`. Requires separate index or full-text search.
2. **Case-sensitivity:** Client normalizes input to lowercase; confirm app enforces it on all mutations.
3. **Typo tolerance:** Fuzzy search (levenshtein, trigrams)? Out of scope for SQLite (use external tool or PostgreSQL FTS).
4. **Pagination default size:** Recommend 20–50 per page. Confirm with UX.
5. **Assignment UI:** Current form posts checkboxes (full list); migrate to HTMX incremental add/remove?

---

## Summary

- **Search:** `.startswith(q)` with `ix_allowedsender_bot_username(bot_id, username COLLATE NOCASE)`.
- **Pagination:** Offset `.offset(page * size).limit(size)` + count query; safe for ≤1000 rows.
- **Per-group:** JOIN + LEFT JOIN to avoid IN-lists; use NOT EXISTS for unassigned picker.
- **Mutations:** Idempotent `add_group_sender` / `remove_group_sender` endpoints; no full-form replace.
- **Webhook:** Single LEFT JOIN query replaces 2-query + IN-list approach; sidesteps parameter limits.
- **Indexes:** Add `ix_allowedsender_bot_username` composite index with `COLLATE NOCASE`.
