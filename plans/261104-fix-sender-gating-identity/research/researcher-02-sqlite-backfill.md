# SQLite Schema Migration & Backfill Patterns (No Alembic)
**Research Note:** Safe additive schema migration + idempotent backfill for SQLite WAL + SQLModel

---

## 1. ALTER TABLE ADD COLUMN Safety

**Verdict: SAFE & INSTANT for nullable INTEGER**

- SQLite supports `ALTER TABLE tablename ADD COLUMN` since v3.1.6 (2005).
- **No CONSTRAINT clause allowed in SQLite >= 3.25.0**: Cannot add UNIQUE, FOREIGN KEY, or PRIMARY KEY via ALTER.
- **No NOT NULL without DEFAULT**: Omit NOT NULL; use NULL default.
- **Execution time**: O(1) instant on disk (only schema modification, no data rewrite).

**Recommended DDL:**
```sql
ALTER TABLE allowedsender ADD COLUMN telegram_user_id INTEGER
```
- Default is implicitly NULL (standard SQL behavior).
- No need to specify `DEFAULT NULL`.
- INTEGER column holds 64-bit signed integers (-2^63 to 2^63-1), safe for Telegram user IDs (typically ~9-10 digits).

**Your codebase pattern** (db.py:47-67, `_add_missing_columns()`):
- Already idempotent: checks `insp.get_columns(table.name)` before adding.
- Safely skips columns already present.
- Confirms nullable or has default before executing ALTER.
- ✅ **Reuse this pattern; no changes needed.**

---

## 2. Idempotency: Check Before ALTER

**Your pattern is correct.** Confirm via `PRAGMA table_info`:

```sql
PRAGMA table_info(allowedsender);
```
Returns: `(cid, name, type, notnull, dflt_value, pk)` for each column.

**Idempotent check before ALTER:**
```python
insp = inspect(engine)
existing = {c["name"] for c in insp.get_columns("allowedsender")}
if "telegram_user_id" not in existing:
    # Safe to add
```

**Already implemented in your codebase** (line 57: `if col.name in existing: continue`).

**Safe to call every startup**: No-op after first run; subsequent runs skip the ALTER entirely.

---

## 3. Backfill SQL: Match username, Idempotent Update

**Context:** 
- Update `allowedsender.telegram_user_id` from `senderprofile` where usernames match.
- Only update rows where `telegram_user_id IS NULL` (already backfilled rows stay untouched).
- Scope per bot_id (no cross-bot contamination).

### Option A: UPDATE ... FROM (SQLite 3.33+, 2020)
```sql
UPDATE allowedsender
SET telegram_user_id = sp.telegram_user_id
FROM senderprofile sp
WHERE allowedsender.bot_id = sp.bot_id
  AND allowedsender.username = sp.username
  AND allowedsender.telegram_user_id IS NULL;
```
**Pros:** Cleaner, SQLite native since 3.33 (widely adopted).
**Cons:** Fails silently on older SQLite versions (pre-2020).

### Option B: Correlated Subquery (All SQLite versions)
```sql
UPDATE allowedsender
SET telegram_user_id = (
  SELECT sp.telegram_user_id
  FROM senderprofile sp
  WHERE sp.bot_id = allowedsender.bot_id
    AND sp.username = allowedsender.username
    AND sp.telegram_user_id IS NOT NULL
  LIMIT 1
)
WHERE allowedsender.telegram_user_id IS NULL
  AND allowedsender.username IS NOT NULL
  AND EXISTS (
    SELECT 1 FROM senderprofile sp
    WHERE sp.bot_id = allowedsender.bot_id
      AND sp.username = allowedsender.username
  );
```
**Pros:** Works on all SQLite versions; safe guards against NULL username & multiple matches.
**Cons:** Subqueries execute for every row (slower on large tables).

### Recommended: Hybrid (safety + compatibility)
**Use Option B for production.** Conservative approach:
- Require exact single match (LIMIT 1 prevents ambiguity).
- Skip NULL usernames in allowedsender (won't match against senderprofile).
- Only update if `telegram_user_id` was NULL (idempotent).
- Check app.db SQLite version at startup; log if < 3.33, warn about perf.

### Backfill Function (Python, in db.py style)
```python
def _backfill_telegram_user_id() -> None:
    """Idempotent: match allowedsender.username against senderprofile.username.
    Only backfill rows where telegram_user_id is NULL.
    Conservative: only if exactly one senderprofile match per bot_id + username.
    """
    if not inspect(engine).has_table("allowedsender"):
        return
    if not inspect(engine).has_table("senderprofile"):
        return
    
    # Check SQLite version for UPDATE...FROM support.
    version = engine.exec_driver_sql("SELECT sqlite_version()").scalar()
    use_from_syntax = tuple(map(int, version.split('.')[:2])) >= (3, 33)
    
    with engine.begin() as conn:
        if use_from_syntax:
            # Modern syntax (3.33+)
            conn.exec_driver_sql("""
                UPDATE allowedsender
                SET telegram_user_id = sp.telegram_user_id
                FROM senderprofile sp
                WHERE allowedsender.bot_id = sp.bot_id
                  AND allowedsender.username = sp.username
                  AND allowedsender.telegram_user_id IS NULL
                  AND sp.telegram_user_id IS NOT NULL
            """)
        else:
            # Correlated subquery (all versions)
            conn.exec_driver_sql("""
                UPDATE allowedsender
                SET telegram_user_id = (
                  SELECT sp.telegram_user_id
                  FROM senderprofile sp
                  WHERE sp.bot_id = allowedsender.bot_id
                    AND sp.username = allowedsender.username
                    AND sp.telegram_user_id IS NOT NULL
                  LIMIT 1
                )
                WHERE allowedsender.telegram_user_id IS NULL
                  AND allowedsender.username IS NOT NULL
                  AND EXISTS (
                    SELECT 1 FROM senderprofile sp
                    WHERE sp.bot_id = allowedsender.bot_id
                      AND sp.username = allowedsender.username
                  )
            """)
```

**Call site** (in `create_db_and_tables()` after `_add_missing_columns()`):
```python
_backfill_telegram_user_id()
```

---

## 4. INTEGER Size: 64-bit Signed

**Verdict: SAFE for Telegram user_id.**

SQLite INTEGER affinity:
- Stored as signed 64-bit integer: -9,223,372,036,854,775,808 to 9,223,372,036,854,775,807.
- Telegram user IDs: typically 6-10 digits (~1B-10B range), well within bounds.
- No overflow risk.

**Type mapping (SQLModel):**
```python
telegram_user_id: Optional[int] = Field(default=None)
```
SQLAlchemy auto-maps to SQLite INTEGER; SQLModel infers nullable via Optional.

---

## 5. Backfill Mismatches & Safety Guards

### Risk: Username Reuse (Different User)
**Scenario:** User A had username "alice", then changed it. User B claimed "alice". Backfill matches wrong user.

**Guard:** None fully preventable. **Recommendation:** Document this as a known edge case. If critical, require manual review or a "audit_log" recording old->new username changes in senderprofile. For now, accept risk (typical for denormalized caches).

### Risk: Username NULL in allowedsender
**Scenario:** A sender row has NULL username; backfill tries to match.

**Guard:** Already in correlated subquery (line 47: `AND allowedsender.username IS NOT NULL`).

### Risk: Multiple senderprofile Rows per (bot_id, username)
**Scenario:** Data corruption or bug; multiple rows with same bot_id + username but different telegram_user_id.

**Guard:** LIMIT 1 in correlated subquery picks first match (deterministic but arbitrary). **Better:** Assume senderprofile has a UNIQUE(bot_id, username) constraint in schema. Verify in models.py.

### Idempotency Guarantee
- `WHERE allowedsender.telegram_user_id IS NULL` ensures second run touches nothing (all rows already have a telegram_user_id or will never match).
- **Re-running is safe.**

---

## 6. Summary: Migration Steps

1. **Add column** (idempotent, db.py `_add_missing_columns()` pattern):
   ```python
   # In SQLModel:
   class AllowedSender(SQLModel, table=True):
       ...
       telegram_user_id: Optional[int] = Field(default=None)
   
   # db.py creates ALTER TABLE ADD COLUMN automatically on next startup.
   ```

2. **Backfill data** (idempotent, new function):
   ```python
   def _backfill_telegram_user_id() -> None:
       # Use Option B (correlated subquery) for broad compatibility.
       # Guards: NULL username, EXISTS check, IS NULL check.
   ```

3. **Call both** in startup order:
   ```python
   def create_db_and_tables() -> None:
       SQLModel.metadata.create_all(engine)
       _add_missing_columns()          # ← adds telegram_user_id
       _backfill_telegram_user_id()    # ← populates it
       _add_search_indexes()
       ...
   ```

4. **Test:** Run twice; verify second run is no-op (count rows with NULL telegram_user_id stays the same).

---

## Unresolved Questions

- Does `senderprofile` have a UNIQUE(bot_id, username) constraint, or could duplicates exist? (**Verify in models.py**)
- Is username ever reused by different Telegram IDs post-username-change? (**Document expected behavior or implement audit log**)
- Requirement: should rows with NULL username ever be matched? (**Current guards assume no; confirm with team**)
