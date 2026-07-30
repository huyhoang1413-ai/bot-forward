# Telegram Bot API: Sender Identification & Username Allowlist Research

## 1. User Object Fields & Username Optionality

### Mandatory Fields
- `id` - numeric user identifier (stable, immutable)
- `is_bot` - boolean
- `first_name` - string

### Optional Fields (Username Among Them)
- `username` - **OPTIONAL**, absent when user has no public username
- `last_name`, `language_code`, `is_premium` — other optional fields

**When username is absent:**
User has not configured a public username in Telegram settings. Privacy-conscious users often skip this step. No frequency data available in official docs, but assumed significant (estimate: 30-50% of casual users may lack usernames).

**Source:** [core.telegram.org/bots/api#user](https://core.telegram.org/bots/api#user)

---

## 2. Username Normalization & Matching Rules

### Case Insensitivity
Telegram usernames are **case-insensitive**. `@JohnDoe` and `@johndoe` resolve to the same user. Display capitalization is preserved, but uniqueness and matching is case-agnostic.

### Character Composition
- Allowed: `a-z`, `0-9`, underscore `_`
- Must start with a letter
- Length: 5-32 characters (minimum 5)
- Leading `@` is a **display convention only**, NOT part of stored username

### Normalization for Allowlist Matching
**Recommended approach:**
```python
# Strip leading @ if present, then lowercase
def normalize_username(username: str) -> str:
    return username.lstrip('@').lower()

# Store allowlist entries normalized:
ALLOWLIST = {'johndoe', 'admin_bot', 'alice123'}

# Compare incoming message sender:
sender_username = message.from_user.username
if sender_username and normalize_username(sender_username) in ALLOWLIST:
    # forward message
```

**Sources:**
- [Medium: Telegram Usernames](https://medium.com/kirobo-io/about-telegram-usernames-and-how-to-set-them-58cf11c6e49d)
- [BotNameFinder: Telegram Bot Username Rules](https://botnamefinder.com/blog/telegram-bot-username-rules)

---

## 3. Username Mutability & ID Stability

### Critical Risk: Username Mutability
- Users **CAN** change their username at any time
- Users **CAN** remove their username entirely
- Usernames are **NOT unique over time** — a username released by one user can be claimed by another

### Implications for Allowlist Strategy
**Username-based allowlist is unreliable:**
- Legitimacy drifts if a permitted user changes username
- Impersonation risk if a username is recycled to a new user
- No way to detect when an allowed username was reassigned

**Recommendation: Use numeric `id` as primary key**, optionally cached with username for UX:
```python
# Better approach
ALLOWLIST_IDS = {123456789, 987654321, 555666777}

# Primary check: numeric ID (stable)
if message.from_user and message.from_user.id in ALLOWLIST_IDS:
    # forward

# Optional: cache/display (non-authoritative)
USER_CACHE = {
    123456789: {'username': 'johndoe', 'first_name': 'John'},
}
```

**For user-friendly allowlist entry:** Accept username input, but resolve it to `id` via bot's user database or `/getUser` equivalent (if available). Store `id` as the authority.

---

## 4. Message.from Absence & Special Cases

### When `from` is Absent or Null
1. **Channel posts** — no individual sender, only channel identity
2. **Messages sent on behalf of a chat** (e.g., supergroup/channel auto-forwards) — `from` may be empty, check `sender_chat` instead

### Service Messages
- Join/leave notifications, title changes, etc. — `from` field behavior inconsistent; always validate before access

### Anonymous Group Admins
- Supergroup message posted by anonymous admin → `from` field may be omitted or fake
- **Correct field:** `sender_chat` (contains the supergroup/group identity)
- **Implication:** Cannot reliably filter anonymous admin messages by username since there is no individual user

### Channel Messages & Forwards
- Auto-forwarded channel posts to discussion group → `from` absent, use `sender_chat`
- Manual forwards → `from` may be present (the manual forwarder) OR absent (original sender if forwarded metadata preserved)

### Bot Webhook Updates
If bot has privacy mode OFF and is group admin:
- Full `from` object included for group messages
- If privacy mode ON (default):
  - Only messages directly mentioning or replying to bot include full sender info
  - Other group messages may lack `from` or have limited info

**Source:** [core.telegram.org/bots/api#message](https://core.telegram.org/bots/api#message)

---

## 5. Practical Filtering Logic for Python-Telegram-Bot v21

### Safe Sender Identification Pattern
```python
from telegram import Update
from telegram.ext import ContextTypes

async def forward_if_allowed(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Only process if message exists and has sender
    if not update.message or not update.message.from_user:
        # No sender info — skip
        return
    
    sender_id = update.message.from_user.id
    sender_username = update.message.from_user.username
    
    # Check 1: Numeric ID (primary, stable)
    if sender_id in ALLOWLIST_IDS:
        await context.bot.forward_message(
            chat_id=DEST_CHAT,
            from_chat_id=update.message.chat_id,
            message_id=update.message.message_id
        )
        return
    
    # Check 2: Username (secondary, if configured; case-insensitive)
    if sender_username:
        normalized = sender_username.lower()
        if normalized in ALLOWLIST_USERNAMES:  # also stored lowercase
            # Forward...
            return
    
    # Not allowed — silently drop
```

### Handling Sender_chat (Group/Channel Posts)
```python
if update.message.sender_chat:
    # Message from anonymous admin, channel forward, etc.
    # sender_chat.id = the group/channel's numeric ID
    # Cannot filter by "sender username" — there is none
    sender_chat_id = update.message.sender_chat.id
    if sender_chat_id in ALLOWLIST_CHAT_IDS:
        # Forward from allowed channel/supergroup
        await context.bot.forward_message(...)
```

---

## 6. Bot API 7.x Additions (Sender Context)

### Relevant Fields
- **`sender_boost_count`** (Message field, v7.0+) — how many boosts the sender has given the chat. **Not relevant for sender identity filtering.**
- **`via_bot`** (optional, Message field) — if message sent via another bot, contains that bot's User object. **Not the original sender** — still use `from_user`.
- **`forward_origin`** (optional, Message field, v7.5+) — detailed origin of forwarded messages (who originally sent, which channel, timestamp). **Useful for tracing but adds complexity; simpler to check original `from_user` in most allowlist cases.**

**Practical impact:** `forward_origin` is too advanced for a basic username allowlist; stick with `from_user.id` and `from_user.username`.

---

## Summary: Recommended Allowlist Architecture

| Aspect | Recommendation |
|--------|-----------------|
| **Primary Key** | User `id` (numeric, stable, immutable) |
| **Secondary Key** | User `username` (optional, case-insensitive, mutable) |
| **Normalization** | Strip `@`, lowercase both for comparison |
| **Missing Username** | Silently reject if username is the only criterion; acceptable if ID-based check passes |
| **Mutability Risk** | Use ID whenever possible; username can be recycled |
| **Anonymous/Channel Posts** | Check `sender_chat.id` separately if needed; no username available |
| **Webhook Update Structure** | Always validate `message.from_user` exists before access; may be null in edge cases |

---

## Unresolved Questions

1. **Frequency of missing usernames:** No official stat on what % of Telegram users lack a public username.
2. **Anonymous admin message frequency:** How often are group admins anonymous, vs. identified?
3. **Privacy mode effects on group bots:** Exact behavior under different privacy + admin configurations not fully documented.
