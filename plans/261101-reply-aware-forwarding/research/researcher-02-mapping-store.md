# Research: MESSAGE MAPPING STORE FOR REPLY-AWARE FORWARDING
Date: 2026-11-01

## EXECUTIVE SUMMARY
Implement lightweight `MessageMap` table (bot_id, dest_chat_id, source_chat_id, source_message_id → dest_message_id) with composite index on lookup key + separate index on `created_at` for 3-day pruning. Store mapping AFTER successful job delete in same transaction (SERIALIZABLE) to guarantee atomicity. Insert map on send success before deleting job, not after. Delete rows via periodic worker loop (30-60 min), not on hot path. SQLite WAL + SQLAlchemy bulk ops handle write volume (1 INSERT per delivered msg).

---

## SCHEMA: EXACT DEFINITION & INDEXES

### Core Table
```python
class MessageMap(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    bot_id: str = Field(index=True)  # indexed for queries
    dest_chat_id: str
    source_chat_id: str
    source_message_id: int
    dest_message_id: int
    created_at: datetime = Field(default_factory=utc_now, index=True)  # pruning
    
    # Composite lookup index (bot_id, dest_chat_id, source_chat_id, source_message_id)
    __table_args__ = (
        Index(
            'ix_messagemap_lookup',
            'bot_id', 'dest_chat_id', 'source_chat_id', 'source_message_id'
        ),
        Index('ix_messagemap_created_at', 'created_at'),  # pruning queries
    )
```

**UNIQUE Constraint: NO.** Avoid UNIQUE (bot_id, dest_chat_id, source_chat_id, source_message_id) for idempotency. If job retries after map-insert success, UNIQUE would throw IntegrityError. Instead, idempotency comes from transaction ordering (insert map → delete job atomically). Same (bot_id, dest, src) tuple in a retry is acceptable; lookups always use `first()` and take the most recent anyway. Soft dedup on reads, not writes.

**Migrations:** ALTER ADD COLUMN for `created_at` (default CURRENT_TIMESTAMP nullable). New tables via `create_all()`. No DROP/MODIFY.

---

## CAPTURE FLOW: MINIMAL CONTROL-FLOW CHANGE

### Job Definition (add fields for ALL kinds)
```python
class ForwardJob(SQLModel, table=True):
    # ... existing fields ...
    origin_chat_id: str  # NEW: required for map insert
    origin_message_id: int  # NEW: required for map insert
    dest_message_id: Optional[int] = None  # filled by send_fn
```

### Worker Loop Sequence
```python
async def process_outbox_job(session: Session, job: ForwardJob):
    # 1. SEND & CAPTURE dest_message_id
    dest_msg_id = await send_fn(job)  # send_fn NOW RETURNS int (dest message id)
    
    # 2. INSERT MAP in transaction
    msg_map = MessageMap(
        bot_id=job.bot_id,
        dest_chat_id=job.dest_chat_id,
        source_chat_id=job.origin_chat_id,  # from job
        source_message_id=job.origin_message_id,  # from job
        dest_message_id=dest_msg_id,
        created_at=utcnow()
    )
    session.add(msg_map)
    
    # 3. DELETE JOB (SAME TRANSACTION)
    session.delete(job)
    session.commit()  # atomic: both succeed or both rollback
```

**Rationale:** Keep per-dest FIFO (jobs processed by dest_chat_id order preserved). If map-insert fails (DB error), job is NOT deleted (stays queued). Commit atomicity ensures no orphaned jobs. On retry, send is idempotent (send_fn handles dup detection), map insert is harmless (no UNIQUE, just adds duplicate row; next reply picks latest).

---

## RESOLUTION TIMING: SEND-TIME RECOMMENDED

### Option A: Build-time (bake dest_message_id into job)
- **Pro:** Zero lookup on reply; reply job already has dest_id.
- **Con:** Can't capture real dest_message_id from API (most gateways don't return it immediately). Would need webhook callback or polling. Adds latency before job is queueable.
- **Verdict:** Impractical for real gateways.

### Option B: Send-time (worker looks up on reply) ← CHOSEN
- **Pro:** Captures real dest_message_id from send response. Simple, natural.
- **Con:** Race if original msg still queued when reply arrives. Original not yet in MessageMap.
- **Mitigation:** Quoted fallback—reply worker checks map; if not found, quote the origin (inline text "Re: [original sender] [original text]"). Acceptable UX.

**Guarantee:** Per-dest FIFO ordering ensures original job completes (and map is inserted) BEFORE reply job is dequeued for same dest_chat_id.

---

## RETENTION & PRUNING: PERIODIC BACKGROUND TASK

### Deletion Query
```python
# Run every 30–60 minutes, NOT on hot path
def prune_old_maps(session: Session, days: int = 3):
    cutoff = utcnow() - timedelta(days=days)
    stmt = delete(MessageMap).where(MessageMap.created_at < cutoff)
    result = session.exec(stmt)
    session.commit()
    return result.rowcount
```

### Volume & Index Cost
- **Write volume per forward:** 1 INSERT (MessageMap) + 1 DELETE (ForwardJob). ≈ 2 rows touched.
- **Storage:** 1 row per delivered message per dest. 100 msgs/day × 10 bots × 50 dests = 50K rows. 3-day retention = 150K rows max. Negligible (< 10 MB with indexes).
- **Index cost:** Composite (4-col) + created_at (1-col) = 2 indexes. Overhead: ~20% on INSERT. Acceptable for << 1M row table.
- **Pruning:** `DELETE WHERE created_at < ?` uses `created_at` index, runs in seconds for 50K rows.

---

## WRITE VOLUME & PERFORMANCE

### Per-Message Cost
- 1 INSERT (MessageMap) on send success
- 1 DELETE (ForwardJob) on send success
- Ratio: small table, no joins, composite index lookup negligible.

**Batching:** Not needed. SQLAlchemy + SQLite handle 1 INSERT + 1 DELETE per transaction smoothly. WAL mode makes writes sequential & fast. For high throughput (>100 msgs/sec), consider connection pooling (SQLAlchemy default handles it).

**Idempotent retries:** If send succeeds but connection drops before commit, job remains in queue. Retry sends again (send_fn must be idempotent). Map insert on retry is harmless (duplicate row, no UNIQUE). Worker takes latest map on reply lookup.

---

## IDEMPOTENCY & RETRY SEMANTICS

### Failure Scenarios

| Scenario | Outcome |
|----------|---------|
| Send fails | Job stays in queue, map not inserted. Retry. |
| Send succeeds, map insert fails | Job stays in queue, map not inserted. Retry sends again (idempotent). |
| Send + map insert succeed, job delete fails | Job deleted in next iteration (ephemeral error). If process crashes, job stays—OK, will be re-sent on recovery. |
| All succeed, commit hangs | Both map + job commit atomically (SQLite WAL ensures this). No double-send. |

### Best Practice: Transaction Order
1. **Capture** dest_message_id from send response.
2. **INSERT** MessageMap row (add to session).
3. **DELETE** ForwardJob row (mark for deletion in session).
4. **COMMIT** (both operations atomic).

**Why this order?** If crash between steps 2 & 4, both changes are rolled back. No orphaned map without job. SQLAlchemy + SQLite guarantee atomicity.

---

## SOURCES & CITATIONS

- **SQLAlchemy 2.0 Indexes & Constraints:** https://docs.sqlalchemy.org/en/20/core/constraints.html
- **SQLAlchemy ORM Transactions:** https://docs.sqlalchemy.org/en/20/orm/session_basics.html#framing-out-a-begin-commit-rollback-block
- **SQLite WAL Mode:** https://www.sqlite.org/wal.html (transaction isolation, checkpoint, performance)
- **SQLite DELETE Syntax:** https://www.sqlite.org/lang_delete.html (supports WHERE, LIMIT, ORDER BY for pruning)
- **SQLModel Docs:** https://sqlmodel.tiangolo.com (SQLAlchemy + Pydantic ORM)

---

## UNRESOLVED QUESTIONS

1. **Send function signature:** Does `send_fn` return `int` (dest_message_id) for all gateway types (Telegram, Discord, etc.)? Or gateway-agnostic wrapper needed?
2. **Quoted fallback UX:** Is inline quote acceptable if original not yet mapped? Or require re-queue reply?
3. **Pruning race:** Can a reply job query MessageMap while pruning deletes rows? (Ans: Yes, WAL readers isolated. But rare race on 3-day boundary acceptable.)
4. **Map lookup on reply:** Single row expected per (bot_id, dest_chat_id, source_chat_id, source_message_id)? Or replying to same source msg multiple times in different dest chats? (Latter = dedup by (bot_id, dest_chat_id, source_message_id)?)
