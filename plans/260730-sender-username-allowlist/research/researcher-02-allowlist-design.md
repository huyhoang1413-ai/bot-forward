# Sender Allowlist Design for Telegram Message Forwarder

## 1. Whitelist Semantics: EMPTY → FORWARD EVERYONE (Backward-Compatible)

**Recommendation: Empty allowlist = forward all messages**

Rationale:
- Existing routes without allowlist data should continue working (backward-compat)
- MVP: feature is opt-in, not default-deny
- Admin explicitly adds usernames to enable filtering
- Aligns with principle of least surprise: "no rules = no restrictions"
- Per [Auto Forward Telegram bot docs](https://docs-v2.autoforwardtelegram.com/filters/whitelist-users), whitelist is an *additive* filter—only listed users pass through

Implementation: `if not allowlist: return ALLOW_ALL`

---

## 2. Scope: Per-Bot (Applies to All Routes)

**Recommendation: Per-BOT allowlist, not per-route or per-source-chat**

Rationale (KISS/YAGNI):
- User has bidirectional bridge between two chats; admin wants to "only forward from these 5 users"
- That intent applies to *both directions* (source→dest and dest→source)
- Per-route = 2× config overhead + duplication
- Per-source-chat = admin must list users separately for each endpoint (friction)
- **One allowlist per bot = one source of truth**

Schema: `bot_id → allowed_username`

Multiple bots can have independent allowlists; routes inherit the bot's allowlist automatically.

---

## 3. Data Model: Normalized Separate Table

**Recommendation: `allowed_sender(id, bot_id, username)` table**

```sql
CREATE TABLE allowed_sender (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    username TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(bot_id, username),
    FOREIGN KEY (bot_id) REFERENCES bot(id) ON DELETE CASCADE
);
```

**Why NOT comma-list column:**
- Normalization: easier to query "is username X allowed for bot Y?"
- Allows indexing: `CREATE INDEX idx_bot_username ON allowed_sender(bot_id, username)`
- CRUD simpler: add/remove one row, not parse/stringify
- Future features: per-username metadata (e.g., added_date, admin notes)

**Normalization rules:**
- Store username **lowercase** (telegram usernames are case-insensitive)
- Strip leading `@` on insert: normalize `"@alice"` → `"alice"`
- Display with `@` prefix in UI (cosmetic only)

---

## 4. Matching: Username as Primary, User ID as Fallback

**Recommendation: Match by username primary key**

Rationale:
- Admins know usernames; user_id requires running `/getid` or API call
- Usernames less stable than IDs but more usable (UX wins)
- Some users have no username (private accounts)
- **For MVP: username-only; ID matching is YAGNI**

In `decide_action()` pure function:
```python
def is_sender_allowed(bot_id: int, message) -> bool:
    username = message.from_user.username  # May be None
    if username is None:
        return False  # No username = not on list
    
    allowed = db.query(allowed_sender).filter_by(
        bot_id=bot_id,
        username=username.lower()
    ).first()
    return allowed is not None
```

**Note:** If message lacks username, default-deny (safe for MVP).

---

## 5. Admin Panel UX (Jinja Server-Rendered)

**Minimal add/remove interface:**

```html
<div class="allowed-senders">
  <h3>Allowed Senders for Bot: {{ bot.name }}</h3>
  
  <form method="POST" action="/bots/{{ bot.id }}/allowed-sender">
    <input type="text" name="username" placeholder="alice" required>
    <button type="submit">Add</button>
  </form>
  
  {% if bot.allowed_senders %}
    <ul>
    {% for sender in bot.allowed_senders %}
      <li>
        @{{ sender.username }}
        <form method="POST" action="/bots/{{ bot.id }}/allowed-sender/{{ sender.id }}/delete" style="display:inline;">
          <button type="submit">Remove</button>
        </form>
      </li>
    {% endfor %}
    </ul>
  {% else %}
    <p><em>No restrictions (all senders forwarded)</em></p>
  {% endif %}
</div>
```

**Validation:**
- Input: regex `^[a-zA-Z0-9_]{5,32}$` (telegram username rules)
- Check for duplicates before insert
- Provide success/error toast feedback

---

## 6. Real-World Open-Source Examples

### 1. [Auto-Forward-Messages Bot](https://github.com/redf0x1/Auto-Forward-Messages)
- Implements whitelist/blacklist via separate user lists
- Users add by username or ID: `/whitelist add @alice`
- Stores in JSON or DB per chat
- Applies per-route context

### 2. [simple-telegram-forwarder](https://github.com/smaugfm/simple-telegram-forwarder)
- Regex-based message filtering (not user-based)
- Supports optional source-chat filtering
- Config-driven (not DB); minimal UX

### 3. [telegram-forward-user-bot](https://github.com/PetroVoronov/telegram-forward-user-bot)
- Full MTProto via gram-js
- Configurable via intuitive menu
- Supports filter by user type (admin/bot/regular)
- Scope: per-bridge, not per-route

**Consensus:** All prod bots support whitelist by username/ID; per-bot scope is standard for bidirectional bridges.

---

## 7. Block List vs. Allow List Semantics

**Recommendation: Allow list (whitelist) for MVP**

Why:
- "Only forward from these users" is clearer intent
- Safer for admin: explicit approval
- Blacklist requires "forward everyone except X" (implicit—harder to audit)
- Align with [Auto Forward docs terminology](https://docs-v2.autoforwardtelegram.com/fundamentals/whitelist-create-and-management)

Naming: `allowed_sender` table (not `blocklist`); UI copy: "Allowed Senders"

---

## 8. Implementation Checklist (MVP Scope)

1. **DB:** Add `allowed_sender(bot_id, username)` table + index
2. **API Route:** `POST /bots/<bot_id>/allowed-sender` (add), `DELETE /bots/<bot_id>/allowed-sender/<id>` (remove)
3. **Pure Function:** Update `decide_action()` to check allowlist; empty list = allow all
4. **Admin Panel:** Simple add/remove form (Jinja template)
5. **Validation:** Username regex + case-normalization on insert
6. **Testing:** Unit test `decide_action()` with allowlist present/empty; integration test CRUD

---

## Unresolved Questions

1. Should we support filtering by user_id as fallback for users without username? (Defer to v2; MVP username-only)
2. Bulk import of allowlist (CSV/paste)? (YAGNI; single-add MVP)
3. Admin audit log for who added/removed senders? (YAGNI unless user asks)

---

## References

- [Auto Forward Telegram Messages - Whitelist Users](https://docs-v2.autoforwardtelegram.com/filters/whitelist-users)
- [Auto Forward Telegram Messages - Whitelist Create & Management](https://docs-v2.autoforwardtelegram.com/fundamentals/whitelist-create-and-management)
- [Auto-Forward-Messages (GitHub)](https://github.com/redf0x1/Auto-Forward-Messages)
- [simple-telegram-forwarder (GitHub)](https://github.com/smaugfm/simple-telegram-forwarder)
- [telegram-forward-user-bot (GitHub)](https://github.com/PetroVoronov/telegram-forward-user-bot)
