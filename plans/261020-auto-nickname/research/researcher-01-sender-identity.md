# Telegram Bot API: Sender Identity Research
**Date:** 2026-10-20 | **Goal:** Capture sender `user_id` + `first_name` for auto-nickname feature

---

## 1. `message.from` (User Object) — Core Sender Fields

### Schema (https://core.telegram.org/bots/api#user)
| Field | Type | Optionality | Notes |
|-------|------|-------------|-------|
| `id` | Integer | **Required** | Stable user ID; safe for 64-bit storage |
| `is_bot` | Boolean | **Required** | True if sender is a bot |
| `first_name` | String | **Required** | Display name — ALWAYS present for real users |
| `last_name` | String | Optional | May be absent |
| `username` | String | Optional | @ handle; bot currently reads this only |
| `language_code` | String | Optional | User's language preference |

### Key Finding
✅ **`first_name` IS ALWAYS PRESENT** for a real user account.  
✅ **`from.id`** is the stable key for deduplication.  
✅ Recommendation: Use `from.id` + `from.first_name` as the auto-nick tuple.

---

## 2. When `from` is ABSENT — Alternative Identity Sources

### Reference: https://core.telegram.org/bots/api#message (Message schema)

#### Case A: Anonymous Group Administrator
- **Trigger:** Supergroup admin posts anonymously.
- **`from` field:** Absent or contains a fake User object (backward compat).
- **Alternative identity:** `sender_chat` (Chat object, the supergroup).
- **Available info:** Chat title, type (supergroup), but NO individual user_id.
- **Recommendation:** Skip auto-nick capture (no real user identity).

#### Case B: Channel Auto-Forward to Discussion Group
- **Trigger:** Message auto-forwarded from channel → linked discussion group.
- **Fields:** `is_automatic_forward = true`, `sender_chat` = the channel.
- **`from` field:** May be absent.
- **Available info:** Channel chat object, but NO individual poster identity.
- **Recommendation:** Skip auto-nick capture.

#### Case C: Message on Behalf of Channel
- **Trigger:** Business account or other entity sends via channel.
- **Fields:** `sender_chat` = the channel/account, `from` may be absent.
- **Available info:** Chat object only.
- **Recommendation:** Skip auto-nick capture.

#### Case D: Service Messages
- **Trigger:** Automatic system messages (member join, kick, etc.).
- **`from` field:** Absent (not a user action).
- **Alternative:** No direct identity; context only.
- **Recommendation:** Skip (not applicable to user-generated messages).

### Summary Rule
**If `from` is absent or null → skip auto-nick capture.** When `from` is present, it is authoritative for user identity.

---

## 3. Forwarded Messages — Which Sender Matters?

### Reference: https://core.telegram.org/bots/api#message (forward_origin)

**Scenario:** User A forwards User B's message into the group.

#### Field Mapping
| Field | Points to | Use for auto-nick? |
|-------|-----------|-------------------|
| `from` | User A (the forwarder/actual in-group poster) | ✅ **YES — use this** |
| `forward_origin` (MessageOrigin type) | Original message metadata (User B, original chat, etc.) | ❌ No (legacy field; modern API uses forward_origin) |

### Finding
✅ **Use `from`, NOT `forward_origin`.**  
The in-group poster (`from`) is the sender whose name should be captured for the auto-nick, since they are the one interacting with the bot's group at that moment.

---

## 4. Bots as Senders — `from.is_bot`

### Reference: https://core.telegram.org/bots/api#user (is_bot field)

- **`from.is_bot = true`** → sender is a bot account.
- **No mandatory exclusion**, but context-dependent:
  - If capturing *human* sender names for readability → skip bots (is_bot filter).
  - If capturing *all* senders → include, note in label that sender is automated.

### Recommendation
Capture bots too (include in tuple), but:
- Optional: Filter `is_bot == false` in UI/settings if feature prefers human-only nicks.
- Store `is_bot` flag alongside auto-nick for debugging.

---

## 5. Proactive Lookup — Refresh Member Names Without Message

### Reference: https://core.telegram.org/bots/api#getchatmember

#### getChatMember Method
**Signature:**
```
getChatMember(chat_id: int | str, user_id: int) → ChatMember
```

**ChatMember.user fields:**
- Same User object schema: `id`, `is_bot`, `first_name`, `last_name`, `username`, `language_code`, etc.

#### Findings
✅ **getChatMember WORKS for groups the bot is in.**  
✅ **Returns `ChatMember.user.first_name`** — can be used to refresh/sync names.  
❌ **Cannot lookup by `@username` alone** — requires numeric `user_id`.

#### Use Case: "Refresh Names" Button
- Bot maintains a `{user_id → first_name}` mapping from messages.
- Button triggers: `getChatMember(group_id, user_id)` for all known IDs.
- Updates stale names (users may have changed their display name).
- **Limitation:** Only works if bot has already captured `user_id` from a message.

#### No Direct Username Resolution
There is NO Bot API method to resolve `user_id` from a `@username` string. Usernames are unique but only resolvable:
1. When user messages the bot directly.
2. When user is mentioned in a message (`entities[].user`).
3. From prior captures in your DB.

---

## 6. Edited Messages — Same Identity Structure

### Reference: https://core.telegram.org/bots/api#editmessagetext

**Update type:** `edited_message` (in webhook).

**Structure:** Complete Message object (identical to original message).

**Fields `from` and `sender_chat`:**
- ✅ Present in edited message.
- ✅ Same values/structure as original.
- ✅ No changes when edit occurs.

**Implication for auto-nick:**
- Edited messages do NOT require re-capturing the sender name.
- The original `from` identity persists.

---

## Recommendations & Implementation Rules

### Capture Rule
**Condition:** `if message.get('from') and message['from'].get('first_name'):`

1. Extract: `user_id = message['from']['id']`
2. Extract: `first_name = message['from']['first_name']`
3. Store tuple: `(user_id, first_name)` in auto-nick mapping.
4. Optional filter: `if not message['from'].get('is_bot')` (skip bots if desired).

### Skip Cases
- ❌ `from` is None/absent.
- ❌ Anonymous admin post (`sender_chat` present, `from` absent).
- ❌ Channel auto-forward (`is_automatic_forward = true`).
- ❌ Service messages.

### Future: Name Refresh
- Store `user_id → first_name` mapping in database.
- On user request or periodic sync: call `getChatMember(chat_id, user_id)` for known users.
- Update stale names.
- No direct @username lookup exists.

---

## Unresolved Questions

1. **Backward compat**: Do older Telegram clients send `from` when posting anonymously in a supergroup? (Modern API uses `sender_chat`; docs may not reflect client behavior.)
2. **Business account edge case**: When a user sends via a business account (`sender_chat` = business), is `from` the user or the business? Needs test data.
3. **API version drift**: Are there any beta or regional API variations in `Message.from` presence?

---

## Source URLs
- https://core.telegram.org/bots/api#message
- https://core.telegram.org/bots/api#user
- https://core.telegram.org/bots/api#getchatmember
- https://core.telegram.org/bots/api#messageorigin
