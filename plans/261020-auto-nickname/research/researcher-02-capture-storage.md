# Research Report: Capture-Once Sender Storage & Display-Name Labeling

**Date**: 2026-10-20

## Executive Summary

For high-frequency webhook senders, SQLAlchemy 2.0 provides `insert().on_conflict_do_nothing()` (or SQLite's native `INSERT OR IGNORE`) to implement capture-once semantics atomically—no race condition between SELECT-then-INSERT. A per-process in-memory `set[(bot_id, user_id)]` cache eliminates redundant DB writes for repeat senders; on process restart, one harmless upsert re-checks. Schema: `SenderProfile(bot_id, telegram_user_id, first_name, label_override, username, captured_at)` with `UniqueConstraint(bot_id, telegram_user_id)`. Label resolution: manual override > auto-nickname flag-gated first_name > existing AllowedSender label. Hot path: ≤1 SELECT for label (folded into existing route/sender queries) + ≤1 INSERT on first sighting.

## 1. Capture-Once Upsert in SQLite via SQLModel/SQLAlchemy

### SQLAlchemy 2.0 Approach: `insert().on_conflict_do_nothing()`

**Recommended Pattern (Option B)**:
```python
from sqlalchemy import insert
from sqlmodel import Session, SQLModel

class SenderProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    telegram_user_id: int
    first_name: str
    label_override: str | None = None
    username: str | None = None
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    
    __tablename__ = "sender_profile"
    
    class Config:
        # Add unique constraint at table level if SQLModel doesn't handle it
        pass

# In webhook handler:
stmt = insert(SenderProfile).values(
    bot_id=bot_id,
    telegram_user_id=user_id,
    first_name=first_name,
    username=username,
    captured_at=datetime.utcnow()
).on_conflict_do_nothing(
    index_elements=["bot_id", "telegram_user_id"]
)
session.execute(stmt)
session.commit()
```

**Why this works**:
- Atomic: single SQL statement, no race condition
- Native SQLite support via `INSERT ... ON CONFLICT DO NOTHING`
- Returns nothing on conflict → idempotent
- `first_name` is never overwritten; on re-sighting, insert silently fails

**Alternative (Option A): SELECT-then-INSERT** — **DO NOT USE**
- Susceptible to race condition: two concurrent webhooks both pass the SELECT, both attempt INSERT
- Doubles query count for repeat senders
- SQLite WAL mode mitigates but doesn't eliminate under high contention

**SQLite-Native (Option C): INSERT OR IGNORE**
- Equivalent to `on_conflict_do_nothing()` in performance
- Less portable across databases; stick with SQLAlchemy abstraction

### UniqueConstraint Definition

Define at table creation:
```python
from sqlalchemy import UniqueConstraint

class SenderProfile(SQLModel, table=True):
    ...
    __table_args__ = (
        UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_user"),
    )
```

Or via SQLModel metadata on table creation. Ensure migration adds this constraint.

## 2. Avoid DB Write on Every Message: In-Memory Cache

### Pattern: Per-Process Seen Set

```python
class SenderProfileCache:
    def __init__(self):
        self._seen: set[tuple[int, int]] = set()  # (bot_id, user_id)
    
    def mark_seen(self, bot_id: int, user_id: int) -> bool:
        """Returns True if newly seen (needs DB check), False if cached."""
        key = (bot_id, user_id)
        if key in self._seen:
            return False
        self._seen.add(key)
        return True
    
    def clear(self):
        """For testing; also call on graceful shutdown if needed."""
        self._seen.clear()

# Global instance
_sender_cache = SenderProfileCache()

# In webhook handler:
bot_id, user_id = ..., ...
if _sender_cache.mark_seen(bot_id, user_id):
    # First sighting in this process; try to insert
    stmt = insert(SenderProfile).values(...).on_conflict_do_nothing(...)
    session.execute(stmt)
else:
    # Cache hit; skip DB entirely
    pass
```

### Invalidation on Process Restart

- Process restarts → cache clears automatically
- On next boot, first sighting attempts insert → `on_conflict_do_nothing()` silently succeeds (idempotent)
- One redundant upsert per restart per user: harmless, covered by constraint

### Memory Bounds

For ~10k users per bot with one key pair per sender:
- Memory: `10k * 2 ints * 8 bytes = 160 KB` per bot
- Negligible; well below process footprint

If multi-bot, scale linearly. Growing unbounded over 30+ days is acceptable (stale cache = one extra insert attempt).

## 3. Schema Design & Additive Migration

### Proposed SenderProfile Schema

```python
class SenderProfile(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    
    # Unique composite key
    bot_id: int = Field(index=True)  # Existing index for per-bot queries
    telegram_user_id: int
    
    # Captured on first sighting, never overwritten
    first_name: str
    
    # Admin override (e.g., user changed preferred name)
    label_override: str | None = Field(default=None, nullable=True)
    
    # Refreshed on every sighting (users update usernames)
    username: str | None = Field(default=None, nullable=True)
    
    # Metadata
    captured_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
    
    __tablename__ = "sender_profile"
    __table_args__ = (
        UniqueConstraint("bot_id", "telegram_user_id", name="uq_bot_user"),
        # Index for UI list/search by first_name or username
        Index("ix_sender_profile_name_search", "bot_id", "first_name"),
    )
```

### Additive Migration (SQLModel)

```python
# In migration or on app startup (if using metadata.create_all):
from sqlmodel import SQLModel
from bot.db import engine

# Called once at startup
SQLModel.metadata.create_all(engine)
```

Or explicit SQL:
```sql
CREATE TABLE IF NOT EXISTS sender_profile (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    telegram_user_id INTEGER NOT NULL,
    first_name TEXT NOT NULL,
    label_override TEXT,
    username TEXT,
    captured_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bot_id, telegram_user_id)
);
CREATE INDEX IF NOT EXISTS ix_sender_profile_name_search 
  ON sender_profile(bot_id, first_name);
```

**Why additive**: nullable columns can be added safely; new table is empty and non-blocking.

## 4. Label Precedence & Resolution

### Resolution Function (Pure, Testable)

```python
def resolve_sender_label(
    bot_id: int,
    user_id: int,
    auto_nick_enabled: bool,
    session: Session,
) -> str | None:
    """
    Resolve effective label for message sender.
    Precedence: label_override > (auto_nick && first_name) > None
    
    Returns label string to prepend as [label], or None for no label.
    """
    # Lookup SenderProfile (may not exist if feature newly deployed)
    profile = session.query(SenderProfile).filter(
        SenderProfile.bot_id == bot_id,
        SenderProfile.telegram_user_id == user_id,
    ).first()
    
    if profile and profile.label_override:
        return profile.label_override
    
    if auto_nick_enabled and profile and profile.first_name:
        return profile.first_name
    
    return None
```

### Existing AllowedSender.label Fallback

If SenderProfile does not exist (new feature on existing bot), fall back to:
```python
def resolve_sender_label(
    bot_id: int,
    user_id: int,
    auto_nick_enabled: bool,
    session: Session,
) -> str | None:
    profile = session.query(SenderProfile).filter_by(
        bot_id=bot_id,
        telegram_user_id=user_id,
    ).first()
    
    if profile:
        if profile.label_override:
            return profile.label_override
        if auto_nick_enabled and profile.first_name:
            return profile.first_name
    
    # Fallback to AllowedSender.label if no profile
    allowed = session.query(AllowedSender).filter_by(
        bot_id=bot_id,
        telegram_user_id=user_id,
    ).first()
    if allowed and allowed.label:
        return allowed.label
    
    return None
```

**Precedence**:
1. `SenderProfile.label_override` (manual admin set)
2. `SenderProfile.first_name` (auto-captured, gated by `auto_nick_enabled` flag)
3. `AllowedSender.label` (legacy, backward compat)
4. `None` (no label)

## 5. Hot-Path Cost & Query Folding

### Existing Message Forwarding Path

Current webhook → query routes → query senders → forward message.

### Proposed Addition

```python
async def handle_group_message(update: Update, session: Session):
    bot_id, user_id = update.bot_id, update.from_user.id
    first_name = update.from_user.first_name
    username = update.from_user.username
    
    # 1. Capture sender (≤1 INSERT if not cached)
    if _sender_cache.mark_seen(bot_id, user_id):
        stmt = insert(SenderProfile).values(
            bot_id=bot_id,
            telegram_user_id=user_id,
            first_name=first_name,
            username=username or "",
            captured_at=datetime.utcnow(),
        ).on_conflict_do_nothing(index_elements=["bot_id", "telegram_user_id"])
        session.execute(stmt)
    
    # 2. Resolve label for message (can fold into existing route query)
    label = resolve_sender_label(bot_id, user_id, auto_nick_enabled=True, session=session)
    
    # 3. Forward with [label] prefix (existing logic, shift entity offsets)
    await forward_message(update, label, session)
```

### Query Count

- **First sighting**: 1 INSERT (on_conflict_do_nothing) + 1 SELECT for label = 2 queries
- **Repeat sighting (cached)**: 1 SELECT for label = 1 query
- **Repeat sighting (label cached too)**: 0 queries (optional optimization)

### Can We Fold into Existing Queries?

**Partially**: If `forward_message()` already queries routes or AllowedSender, we can add a LEFT JOIN to `SenderProfile` in that same query:

```python
# Pseudo-code in forward_message:
route = session.query(Route).join(
    SenderProfile, 
    (Route.bot_id == SenderProfile.bot_id) & (Route.telegram_user_id == SenderProfile.telegram_user_id),
    isouter=True
).filter(...).first()

# Now route contains joined SenderProfile, extract label
label = resolve_from_joined_profile(route.sender_profile, ...)
```

**Recommendation**: Fold the label resolution SELECT into the existing route/sender queries. Keep capture INSERT separate and gated by cache.

## 6. Sources & References

### SQLAlchemy 2.0 & SQLite

- [SQLAlchemy 2.0 SQLite Dialect](https://docs.sqlalchemy.org/en/20/dialects/sqlite.html)
- [SQLAlchemy on_conflict_do_nothing() Discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/9675)
- [SQLAlchemy Conflict Statements Returning Discussion](https://github.com/sqlalchemy/sqlalchemy/discussions/10512)

### Idempotent Patterns & Webhooks

- [Idempotent Database Inserts: Getting It Right](https://dnnsthnnr.com/writing/idempotent-database-inserts-getting-it-right)
- [Idempotent Webhooks - Automation Pattern Guide 2026](https://webhookagent.com/automation-pattern-2026-04-28-idempotent-webhooks)
- [Webhook Architecture Fundamentals: Idempotency in Webhooks](https://www.webhook-architecture.com/webhook-architecture-fundamentals-design-patterns/idempotency-in-webhooks/storing-idempotency-keys-in-postgres/)

### FastAPI Caching & Cache Invalidation

- [How to Implement Cache Invalidation in FastAPI](https://oneuptime.com/blog/post/2026-02-02-fastapi-cache-invalidation/view)
- [FastAPI Cache Examples - In-Memory](https://github.com/long2ice/fastapi-cache/blob/main/examples/in_memory/main.py)
- [Async Without Tears: 10 Patterns for asyncpg + SQLModel](https://medium.com/@bhagyarana80/async-without-tears-10-patterns-for-asyncpg-sqlmodel-72c68aa68f0d)

## Unresolved Questions

1. **Multi-Instance Deployment**: If the bot runs on multiple processes/replicas, should the in-memory cache be shared (Redis) or process-local? Process-local trades off a few redundant inserts for no external dependency.
2. **Username Refresh Frequency**: Should we UPDATE `username` on every message, or only on initial capture? Current rec: refresh on every sighting (low cost, keeps data fresh).
3. **Label Cache Layer**: Should we add a second in-memory cache for resolved labels (label + auto_nick_enabled state)? Would need invalidation on profile updates.
4. **Admin UI for Override**: Who/how sets `label_override`? Admin panel, API, command? Not covered here.
5. **Migration Path for Legacy Bots**: How to handle bots with no SenderProfile rows? Lazy-populate on first sighting, or batch-scan AllowedSender on deploy?
