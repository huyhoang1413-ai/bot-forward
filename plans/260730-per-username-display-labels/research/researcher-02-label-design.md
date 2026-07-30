# Label Design Research: Per-Username Display Prefixes for Telegram Forwarder

**Date:** 2026-07-30 | **Task:** Design per-username display labels for a multi-bot Telegram forwarder web panel (FastAPI + SQLModel + SQLite).

---

## 1. Data Model: Single `label` Column vs Separate Table

### Recommendation: **Add `label` column to existing `AllowedSender` table**

**Rationale (KISS/DRY):**
- Labels are a UI/display concern tightly coupled with the allowlist entry itself
- Admin workflow is unitary: manage per-source-group allowlist → each username has optional label
- Single table avoids N+1 joins, simpler queries, reduced schema complexity
- Natural cardinality: one label per (bot_id, source_chat_id, username) tuple

**Schema:**
```sql
CREATE TABLE AllowedSender (
    bot_id TEXT,
    source_chat_id INTEGER,
    username TEXT,
    label TEXT,  -- NEW: nullable, e.g. "Doby", "Agent", max 50 chars
    created_at DATETIME,
    PRIMARY KEY (bot_id, source_chat_id, username)
)
```

**SQLModel definition:**
```python
class AllowedSender(SQLModel, table=True):
    bot_id: str
    source_chat_id: int
    username: str
    label: Optional[str] = Field(
        default=None,
        max_length=50,
        description="Display label prefix (e.g., 'Doby'). Null = no prefix."
    )
    created_at: datetime = Field(default_factory=datetime.utcnow)
```

**Benefit over separate table:** Eliminates orphan label records, keeps UI form in one place, matches existing admin mental model.

---

## 2. Scope: Allowlist-Only vs "Forward Everyone" Mode

### Recommendation: **Label applies ONLY to allowlisted users**

**Rationale:**
- User's example ("@fbagency999 → label 'Doby'") implies a labeled allowlist workflow
- "Forward everyone" (empty allowlist) is coarse-grained; fine-grained labeling contradicts the mode
- Simpler logic: no label lookup/fallback needed when allowlist is bypassed
- Aligns with principle of least configuration (YAGNI)

**Logic:**
```
IF source_group has allowlist:
    IF username in allowlist:
        forward with label prefix (if label set)
    ELSE:
        drop message (not allowed)
ELSE:  # forward everyone mode
    forward as-is (no labeling logic)
```

**Edge case:** If admin later enables allowlist on a previously "forward all" group, only labeled allowlisted users get prefixed. This is expected behavior.

---

## 3. Label Format, Validation, and Defaults

### Format: **`[Label] ` prefix (with space) for text/caption**

**Validation rules:**
- **Max length:** 50 chars (limits message overhead, fits most use cases)
- **Allowed chars:** alphanumeric, spaces, hyphens, underscores, emoji (unicode-safe)
- **Trimming:** Strip leading/trailing whitespace; no leading/trailing brackets
- **Empty label:** `None` or empty string → no prefix, forward normally

**Prefix placement:**
```
Original message: "Hello team, let's discuss strategy"
With label "Doby": "[Doby] Hello team, let's discuss strategy"

Caption in photo: "Meeting notes"
With label "Docs": "[Docs] Meeting notes"
```

**Implementation detail:** Prepend label during forwarding, before sending via Telegram API.

---

## 4. Real-World Patterns in Telegram Forwarders

### Key patterns from production bots:

**Pattern 1: Prefix with metadata (TeleFeed)**
- [Source](https://telegrambotting.com/tg_feed): Prefixes posts with country code (e.g., `[US] Message text`)
- Use case: Multi-source feeds, editor needs provenance at glance
- Applicable: Simple, fixed-width metadata

**Pattern 2: Tag-based routing (generic forwarders)**
- [Source](https://github.com/SignoreOscuro/telegram-forward-bot): Users reply to messages with tags; bot forwards based on tag
- Use case: Dynamic, user-driven categorization
- Not applicable here: We're admin-configured, not user-driven

**Pattern 3: Bot-name modifiers (MultiFeed)**
- [Source](https://telespace.me/apps/multifeed_bot): Add `~` or `|` to bot name to toggle features (e.g., `MyBot~|`)
- Use case: Config without database
- Trade-off: Not scalable for per-username labels

**Pattern 4: Sender attribution chain (standard forwarder logic)**
- [Source](https://github.com/HKUDS/nanobot/issues/1091): Fallback chain: first_name → username → user_id
- Context: Bots can't distinguish group senders natively; attach sender metadata
- Applicable: We're enhancing with human-readable labels instead of IDs

**Consensus:** Prefix format `[Label] ` is simplest, most readable, aligns with TeleFeed's proven approach.

---

## 5. UX in Admin Panel (Jinja Template)

### Minimal extension to existing "allowed senders" form:

**HTML structure:**
```html
<table id="allowed-senders">
  <thead>
    <tr><th>Username</th><th>Display Label</th><th>Action</th></tr>
  </thead>
  <tbody>
    <!-- For each allowed sender in group: -->
    {% for sender in group.allowed_senders %}
    <tr>
      <td>@{{ sender.username }}</td>
      <td>
        <input type="text"
               name="label_{{ sender.username }}"
               value="{{ sender.label or '' }}"
               maxlength="50"
               placeholder="e.g., Doby"
               class="label-input" />
      </td>
      <td>
        <button onclick="removeSender('{{ sender.username }}')">Remove</button>
      </td>
    </tr>
    {% endfor %}
  </tbody>
</table>

<button onclick="addSender()">+ Add Sender</button>
<button onclick="saveSenders()">Save Labels</button>
```

**Backend endpoint (PATCH):**
```python
@app.patch("/groups/{group_id}/allowed-senders")
async def update_allowed_senders(group_id: int, payload: dict):
    """
    payload = {
        "senders": [
            {"username": "fbagency999", "label": "Doby"},
            {"username": "other_user", "label": ""}
        ]
    }
    """
    for sender_data in payload["senders"]:
        db.query(AllowedSender).filter(
            AllowedSender.username == sender_data["username"],
            AllowedSender.source_chat_id == group_id
        ).update({"label": sender_data["label"] or None})
    db.commit()
```

**UX improvements:**
- Single form for both add/edit senders and labels
- Inline label editing without modal
- Placeholder text suggests format
- Save button batches updates

---

## 6. Edge Cases

### Stickers, Audio, Files (no text/caption):
```
Sticker forwarded from @fbagency999 with label "Doby"
→ [No caption] → Forward sticker as-is, no prefix applied
→ (Stickers don't have caption field in Telegram; label cannot be prepended)
```

**Solution:** Skip label prefix for media without caption. Log intent:
```python
if message.text:
    prefixed = f"[{label}] {message.text}" if label else message.text
    forward_with_text(prefixed)
elif message.caption:
    prefixed = f"[{label}] {message.caption}" if label else message.caption
    forward_with_caption(prefixed)
else:
    # Sticker, audio, etc. → forward as-is
    forward_as_is(message)
```

### User in allowlist but label is null:
```
@agent_username in allowlist, label = None (or empty string)
→ Forward normally, no prefix
→ SELECT label FROM AllowedSender WHERE username = @agent_username
→ result is None → condition `if label: ...` is False → no prefix
```

### Label change after message sent:
- Messages already sent keep original label (correct: label was part of message content)
- Only future messages use new label
- No need to backfill; label is immutable per forwarded message

---

## 7. Implementation Checklist (MVP)

1. **Schema migration:** Add `label TEXT` column to `AllowedSender`; default `None`
2. **Model update:** Extend `AllowedSender` SQLModel with `label` field
3. **Forwarding logic:** Inject `[label] ` prefix in message text/caption before sending
4. **Admin UI:** Add label input field to each allowed-sender row in group edit form
5. **Backend endpoint:** PATCH to update labels (batch or per-username)
6. **Validation:** Enforce max 50 chars, strip whitespace, UTF-8 safe

---

## Sources

- [TeleFeed: Telegram Forwarding Bot](https://telegrambotting.com/tg_feed)
- [Telegram Forward Bot (GitHub)](https://github.com/SignoreOscuro/telegram-forward-bot)
- [MultiFeed Bot: Auto Telegram Messages Forwarder](https://telespace.me/apps/multifeed_bot)
- [Auto Forward Telegram Bot](https://autoforwardtelegram.com/)
- [SQLModel Documentation](https://sqlmodel.tiangolo.com/)
- [SQLModel Field Configuration](https://betterstack.com/community/guides/scaling-python/sqlmodel-orm/)
- [Telegram Sender Attribution Issue](https://github.com/HKUDS/nanobot/issues/1091)

---

## Unresolved Questions

1. **Label persistence UI:** Should changing a label retroactively update in-channel messages? (Answer: No, they're immutable; only affects future.)
2. **Label inheritance:** If same username appears in multiple source groups, use same label or per-group override? (Recommend: per-group for granular control, aligns with table schema.)
3. **Localization:** Should label support non-Latin scripts/RTL text? (Answer: Yes, UTF-8 safe; test with emoji/Chinese.)
4. **Audit trail:** Log who changed labels and when? (Out of scope MVP; consider later if admin disputes arise.)
