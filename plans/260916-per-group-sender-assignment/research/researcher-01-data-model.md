# Data Model Research: Per-Group Sender Assignment

## Status
RESEARCH COMPLETE - Design A (Junction Table) recommended.

---

## 1. Schema Design Comparison

### Design A: Junction Table (RECOMMENDED)
Keep `AllowedSender` as pure global registry. Add `SenderGroupAssignment` junction:

```python
class AllowedSender(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    username: str
    label: str | None = None
    created_at: datetime = Field(default_factory=_now)
    
    __table_args__ = (
        UniqueConstraint("bot_id", "username", name="uq_allowed_sender"),
    )

class SenderGroupAssignment(SQLModel, table=True):
    """Many-to-many: which global senders apply to which source groups."""
    id: int | None = Field(default=None, primary_key=True)
    allowed_sender_id: int = Field(foreign_key="allowedsender.id", index=True)
    source_chat_id: int = Field(index=True)
    # Future: label_override: str | None = None
    created_at: datetime = Field(default_factory=_now)
    
    __table_args__ = (
        UniqueConstraint("allowed_sender_id", "source_chat_id", 
                        name="uq_sender_group_assign"),
    )
```

**Pros:**
- Cleanest schema separation: global declarations vs. per-group assignments.
- Avoids duplication (one `AllowedSender` row per unique username per bot).
- Dedup is built-in—query once, assign to many groups.
- Backward-compat trivial: empty `SenderGroupAssignment` = "global applies everywhere."
- Future label-override extensible without schema changes.
- Standard SQLAlchemy association table pattern.

**Cons:**
- One extra table to manage.
- Webhook query requires a JOIN (mitigated by single query + index on `allowed_sender_id`).

### Design B: Revert `source_chat_id` + Global-Default Flag
Drop `source_chat_id` as sentinel, restore per-group rows with a `is_global: bool` flag:

```python
class AllowedSender(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int
    source_chat_id: int  # actual group ID, or GLOBAL_SOURCE for global
    username: str
    label: str | None = None
    is_global: bool = False  # redundant with source_chat_id==GLOBAL_SOURCE?
    created_at: datetime = Field(default_factory=_now)
    
    __table_args__ = (
        UniqueConstraint("bot_id", "source_chat_id", "username"),
    )
```

**Pros:**
- Single table.
- Backward migration: rename existing schema back.

**Cons:**
- Duplication: per-group copies of same username + label.
- Dedup logic still needed in business layer (complex post-migration).
- Violates DRY; if label changes, must update N rows.
- `is_global` flag redundant—source_chat_id already encodes it.
- Query complexity: "fetch senders for group X" requires UNION of GLOBAL + group-specific rows.

### Design C: Jsonb Config Column (SQLite Limitation)
Store group assignment as JSON in `AllowedSender.assigned_groups` (iffy on SQLite):

**Cons:**
- SQLite has weak JSON support (no proper indexes).
- Webhook query requires JSON text search (slow, no index).
- Schema fragile; schema validation not automatic.
- YAGNI: overcomplicates for a list that fits a junction table.

**Verdict:** Not viable for SQLite + additive migrations.

---

## 2. Recommendation: Design A (Junction Table)

**Rationale:**
- **KISS:** Clear separation of concerns. Global allowlist is read-mostly; assignments are write-rarely.
- **YAGNI:** No redundant flags or JSON hacks.
- **DRY:** One `AllowedSender` row per unique (bot_id, username) pair; update label once, applies to all groups.
- **Backward-compat:** Existing global allowlist continues to work; empty assignments table = "forward everyone" (explicit is clearer than implicit).
- **Extensible:** Add label_override or per-group restrictions later without migration pain.
- **Standard:** SQLAlchemy "association table" is the proven ORM pattern for this scenario.

**Reference:**  
SQLAlchemy docs on association objects/secondary relationships:  
https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#association-object

---

## 3. Migration Plan (Additive-Only)

### Step 1: Add `SenderGroupAssignment` table
Already covered by `SQLModel.metadata.create_all()` on next startup.

### Step 2: Backfill assignments
One-time idempotent migration in `db.py::_add_sender_group_assignments()`:

```python
def _add_sender_group_assignments() -> None:
    """Idempotent: if all AllowedSenders already have assignments,
    this is a no-op. Otherwise, assign existing global senders to ALL
    source groups (preserves 'forward everyone' semantics).
    """
    from app.models import AllowedSender, SenderGroupAssignment, Route
    
    if not inspect(engine).has_table("sendergroupassignment"):
        return
    
    with Session(engine) as session:
        # Groups that exist in this bot.
        existing = session.exec(
            select(SenderGroupAssignment.allowed_sender_id.distinct())
        ).all()
        
        # For each bot, if its senders have no assignments, 
        # assign them to all its source groups.
        for bot_id_val in session.exec(select(AllowedSender.bot_id.distinct())).all():
            senders = session.exec(
                select(AllowedSender).where(AllowedSender.bot_id == bot_id_val)
            ).all()
            
            groups = session.exec(
                select(Route.source_chat_id.distinct())
                .where(Route.bot_id == bot_id_val)
            ).all()
            
            for sender in senders:
                for group_id in groups:
                    # Skip if already assigned.
                    exists = session.exec(
                        select(SenderGroupAssignment).where(
                            SenderGroupAssignment.allowed_sender_id == sender.id,
                            SenderGroupAssignment.source_chat_id == group_id,
                        )
                    ).first()
                    if not exists:
                        assignment = SenderGroupAssignment(
                            allowed_sender_id=sender.id,
                            source_chat_id=group_id,
                        )
                        session.add(assignment)
        session.commit()
```

### Step 3: Remove `source_chat_id` from `AllowedSender` (future, NOT additive)
This is a **breaking change** (column drop); defer to a future destructive migration if/when backward-compat is abandoned. For now, **ignore `source_chat_id` in queries**—it will always be `GLOBAL_SOURCE`.

---

## 4. Webhook Hot-Path Query

**Design A Query (1 round-trip, no N+1):**

```python
# In webhook.py, fetch allowed senders for a specific source_chat_id:
allowed_senders: dict[str, str | None] = {
    row.AllowedSender.username: row.AllowedSender.label
    for row in session.exec(
        select(AllowedSender).join(
            SenderGroupAssignment,
            SenderGroupAssignment.allowed_sender_id == AllowedSender.id,
        ).where(
            AllowedSender.bot_id == bot_id,
            SenderGroupAssignment.source_chat_id == source_chat_id,
        )
    ).all()
}
```

**Indexes needed:**
```python
# In SenderGroupAssignment.__table_args__:
Index("ix_sender_group_assign", "allowed_sender_id", "source_chat_id"),
Index("ix_sender_group_source", "source_chat_id", "allowed_sender_id"),
```

**Performance:**
- Single SELECT with JOIN and two-column WHERE (indexed).
- Result set is small (typically <100 senders per group per bot).
- **No N+1:** one query fetches the entire set for a group.

---

## 5. Backward-Compatibility Semantics

### (a) Empty Assignments for a Group
**Behavior:** If `source_chat_id` has NO `SenderGroupAssignment` rows → **forward everyone from that group**.

**Rationale:** Preserves current "empty allowlist = no gate" semantics. Admin can incrementally assign senders; unassigned groups default to open.

### (b) Sender Assigned to No Groups
**Behavior:** That sender is **not forwarded from any group**, even though they exist in the global list.

**Rationale:** Admin must explicitly "opt in" groups. This is safer than auto-assigning new senders; admin curates carefully.

### (c) Migration Semantics
On first run with the new schema, backfill assigns every existing global sender to **all existing source groups** in that bot. This preserves behavior: if you had `[alice, bob]` globally and 3 groups, you now have 6 assignment rows, same forwarding behavior.

**Transition UI:**
- UI shows the global allowlist (unchanged).
- New panel: "For each group, which global senders apply?" (checkboxes).
- Admin can uncheck senders to exclude them from a group.

---

## 6. Concrete SQLModel Classes + Constraints

```python
# models.py

from sqlalchemy import UniqueConstraint, Index

class AllowedSender(SQLModel, table=True):
    """Global registry of allowed senders (declare once, reuse per group)."""
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    source_chat_id: int = Field(default=GLOBAL_SOURCE, index=True)  # Kept for schema stability; always 0
    username: str  # normalized: lowercase, no leading '@'
    label: str | None = None  # display label
    created_at: datetime = Field(default_factory=_now)
    
    __table_args__ = (
        UniqueConstraint("bot_id", "username", name="uq_allowed_sender_global"),
    )


class SenderGroupAssignment(SQLModel, table=True):
    """Assign global senders to specific source groups."""
    id: int | None = Field(default=None, primary_key=True)
    allowed_sender_id: int = Field(foreign_key="allowedsender.id", index=True)
    source_chat_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)
    
    __table_args__ = (
        UniqueConstraint("allowed_sender_id", "source_chat_id", 
                        name="uq_sender_group_assign"),
        Index("ix_group_sender", "source_chat_id", "allowed_sender_id"),
    )
```

---

## 7. SQLAlchemy + SQLModel References

- **UniqueConstraint:** https://docs.sqlalchemy.org/en/20/core/constraints.html#unique-constraint
- **Composite Indexes:** https://docs.sqlalchemy.org/en/20/core/indexes.html
- **Association Objects:** https://docs.sqlalchemy.org/en/20/orm/basic_relationships.html#association-object
- **SQLModel docs (inherits from SQLAlchemy ORM):** https://sqlmodel.tiangolo.com/

---

## Summary Table

| Aspect | Design A (Junction) | Design B (Revert + Flag) | Design C (JSON) |
|--------|-----|-----|-----|
| **Tables** | 2 | 1 | 1 |
| **Dedup** | ✓ Automatic | ✗ Manual | ✗ Manual |
| **Query Simplicity** | ✓ Single JOIN | ✗ UNION + conditional | ✗ JSON text search |
| **Extensibility** | ✓ label_override ready | ✗ Needs schema redo | ✗ Schema fragile |
| **Backward-Compat** | ✓ Explicit & clean | ✓ Migration pain | ✗ Not viable |
| **Additive Migration** | ✓ Yes | ✓ Yes (backfill only) | ✓ Yes |
| **KISS/DRY** | ✓✓✓ | ✗ Redundant | ✗ Over-engineered |

---

## Unresolved Questions

1. **Label override per group:** Do we need per-group label variants (e.g., "alice" → "[Alice-A]" in group1, "[alice-int]" in group2)? Currently not in scope; Design A makes it trivial to add later.
2. **Audit trail:** Should assignment changes log to a history table? Out of scope unless required.
3. **UI flow:** Admin experience for bulk assignment (e.g., "add alice to groups 1–3")? Defer to UI spec.
