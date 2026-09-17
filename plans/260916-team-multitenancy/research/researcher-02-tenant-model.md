# Multi-Tenant Data Model + Query Isolation Research

## 1. Schema Design

### Team and Bot Models (SQLModel)

```python
# New model
class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_now)

# Modified model
class Bot(SQLModel, table=True):
    # ... existing fields ...
    team_id: int | None = Field(default=None, foreign_key="team.id", index=True)
```

**Why `team_id` nullable:** 
- **Additive migration:** SQLite's `_add_missing_columns()` (lines 47–67 in `db.py`) uses `ALTER TABLE ADD COLUMN` which requires nullable/defaulted cols. Existing bots initially have `team_id=NULL`.
- **Super-admin + legacy:** NULL distinguishes admin-only/legacy bots (created before multitenancy) from team-owned bots.

**Index strategy:** Composite `(team_id, id)` speeds list/filter queries; single `team_id` index added via `_add_missing_columns()`.

**FK constraint:** SQLAlchemy enforces referential integrity; deleting a Team with `team_id` FK references fails (see §5).

---

## 2. Query Scoping Pattern – RECOMMENDATION

**Pattern (b) – DRY helper functions.** Chosen over pattern (a) (inline `.where()`) for maintainability, auditability, and zero-copy IDOR surface.

### Helper Functions (in `services.py` or new `auth.py`)

```python
def visible_bots(session: Session, user_team_id: int | None) -> list[Bot]:
    """List bots visible to a user. Super-admin (team_id=None in context) sees all."""
    if user_team_id is None:
        return session.exec(select(Bot)).all()
    return session.exec(select(Bot).where(Bot.team_id == user_team_id)).all()

def assert_can_access(bot: Bot, user_team_id: int | None) -> None:
    """Raise 403 if user cannot access bot. Call before any mutation."""
    if user_team_id is None:  # super-admin
        return
    if bot.team_id != user_team_id:
        raise HTTPException(status_code=403, detail="Not your team's bot")
```

### Dashboard Query (UI layer)
```python
# In ui.py handler
bots = visible_bots(session, current_user_team_id)
```

### Per-Bot Access Check (route handler)
```python
@app.get("/bots/{bot_id}")
def get_bot(bot_id: int, session: Session = Depends(get_session), 
            user_team_id: int | None = Depends(extract_team)):
    bot = session.get(Bot, bot_id)
    if not bot:
        raise HTTPException(status_code=404)
    assert_can_access(bot, user_team_id)  # <-- IDOR guard
    return bot
```

**Routes requiring `assert_can_access()` (lines 1–100 in routing handlers):**
- `POST /bots/{bot_id}/routes` → create Route
- `DELETE /bots/{bot_id}` → delete Bot
- `PUT /bots/{bot_id}/password` → update access_password_hash
- `GET /bots/{bot_id}/allowed-senders` → list AllowedSender
- `POST /bots/{bot_id}/allowed-senders` → create AllowedSender
- `DELETE /bots/{bot_id}/allowed-senders/{sender_id}` → delete AllowedSender
- `GET /bots/{bot_id}/group-assignments` → SenderGroupAssignment queries
- `POST/DELETE /bots/{bot_id}/group-assignments` → manage assignments

---

## 3. Ownership on Bot Create

**Recommended:** Assign to user's team on create; super-admin gets a team picker (optional).

```python
@app.post("/bots")
def create_bot(bot_data: BotCreate, session: Session, 
               user_team_id: int | None):
    new_bot = Bot(**bot_data.dict())
    
    if user_team_id is None:  # super-admin
        # Option A (picker in UI): new_bot.team_id = request.team_id_to_assign
        # Option B (default team): new_bot.team_id = SYSTEM_TEAM_ID
        # Option C (null/admin-only): new_bot.team_id = None (current behavior)
        pass  # default behavior: team_id = None (admin-only)
    else:
        new_bot.team_id = user_team_id  # regular user's team
    
    session.add(new_bot)
    session.commit()
    return new_bot
```

---

## 4. Legacy/Unowned Bots (`team_id IS NULL`)

**Recommendation:** Super-admin only.

```python
def visible_bots(session: Session, user_team_id: int | None):
    if user_team_id is None:
        return session.exec(select(Bot)).all()  # sees ALL, including NULL
    # Regular users see only their team's bots; NULL bots hidden
    return session.exec(select(Bot).where(Bot.team_id == user_team_id)).all()
```

**One-time backfill (optional, if migrating to mandatory team assignment):**
```python
def _backfill_bots_to_default_team():
    with Session(engine) as s:
        unowned = s.exec(select(Bot).where(Bot.team_id == None)).all()
        for bot in unowned:
            bot.team_id = DEFAULT_TEAM_ID  # or create a "system" team
        s.add_all(unowned)
        s.commit()
```

---

## 5. Cascade & Integrity

| Operation | Recommendation | Rationale |
|-----------|---|---|
| **Delete Team** | Block if non-empty (has users/bots); optional: reassign bots to system team | Prevents orphaned bots; explicit action required |
| **Delete User** | Reassign bots to team ownership; orphan if strict | Preserves bot continuity; alternatively, soft-delete users |
| **Delete Bot** | Cascade delete Routes, AllowedSender, ForwardJob | Bots are leaf; jobs/routes are purely functional |

**Cascade SQL:**
```sql
CREATE TABLE bot (
    team_id INTEGER REFERENCES team(id) ON DELETE RESTRICT,
    -- ... other columns ...
);

CREATE TABLE route (
    bot_id INTEGER REFERENCES bot(id) ON DELETE CASCADE,
    -- ... other columns ...
);

CREATE TABLE forwardjob (
    bot_id INTEGER REFERENCES bot(id) ON DELETE CASCADE,
    -- ... other columns ...
);
```

SQLModel FK defaults to `ondelete="RESTRICT"`; override with `Field(..., foreign_key="team.id", ondelete="CASCADE")` if needed.

---

## 6. Webhook Isolation

**No change needed.** Webhook path remains bot_id + secret header scoped:

```python
# In webhook.py (unauthenticated)
@app.post("/webhook/{bot_id}")
def webhook(bot_id: int, secret: str = Header(...)):
    bot = session.get(Bot, bot_id)
    if not bot or bot.webhook_secret != secret:
        raise HTTPException(status_code=401)
    # Tenancy = purely admin-UI concern
    process_webhook(bot)
```

**Isolation guaranteed at data layer:** webhook references `telegram_bot_id` (globally unique token), not user identity. Tenancy is additive metadata for UI/access control.

---

## 7. Uniqueness: `telegram_bot_id`

**Status:** Remains globally unique (constraint unchanged).

**Implication:** Two teams CANNOT both register the same Telegram bot (one webhook URL per bot token; the webhook dispatcher sends to bot_id, not team). Attempting duplicate across teams still rejected globally.

**Acceptable?** YES. A Telegram bot token is issued once; dual registration would create routing ambiguity. Global uniqueness is correct.

---

## 8. Required Columns Index Additions (in `_add_missing_columns()`)

Already covered by auto-detection; ensure `team_id` defined with `index=True`.

---

## References

- **SQLModel Relationships:** [https://sqlmodel.tiangolo.com/tutorial/fastapi/relationships/](https://sqlmodel.tiangolo.com/tutorial/fastapi/relationships/)
- **Multi-Tenancy Patterns (FastAPI Medium):** [https://medium.com/@hjparmar1944/fastapi-multi-tenant-saas-row-level-security-without-pain-9ef960085bf4](https://medium.com/@hjparmar1944/fastapi-multi-tenant-saas-row-level-security-without-pain-9ef960085bf4)
- **SQLAlchemy Foreign Keys & Cascade:** [https://docs.sqlalchemy.org/en/20/orm/relationship_api.html](https://docs.sqlalchemy.org/en/20/orm/relationship_api.html)
- **SQLite ALTER TABLE Limits:** [https://www.sqlite.org/lang_altertable.html](https://www.sqlite.org/lang_altertable.html) — supports ADD COLUMN only for nullable/defaulted fields (your migration pattern is correct).

---

## Unresolved Questions

1. **User model scope:** Will users be stored in this DB or externally (e.g., .env super-admin + OAuth)? Affects session context design.
2. **Default team for super-admin:** When admin creates a bot without explicit team picker, assign to a "System" team or leave NULL (current)?
3. **Soft-delete teams/users:** Required, or hard deletes acceptable? Impacts audit/data retention.
4. **API key isolation:** Do API keys exist? If so, scoped to team_id or global?
