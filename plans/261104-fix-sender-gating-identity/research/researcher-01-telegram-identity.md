# Telegram Bot API Sender-Identity Model Research
Research date: 2026-11-04 | Scope: Confirm user_id vs username for forwarding bot access gating

## Q1: Is `from.username` OPTIONAL? Mutable?

**Answer: YES, optional. YES, mutable.**

- **Optional:** Marked "Optional" in User object spec. "Username, for private chats, supergroups and channels if available" — many users lack public @username.
- **Mutable:** Telegram allows users to change or remove @username at any time.
- **Implication:** Gating by username breaks for users without one, and breaks when users change username.

Source: core.telegram.org/bots/api#user

---

## Q2: Is `from.id` ALWAYS present, stable, unique, and 64-bit safe?

**Answer: YES to all.**

- **Always present:** `from.id` marked as required (no "Optional" tag). "Unique identifier for this user or bot" — mandatory for User objects.
- **Stable:** Numeric user_id does not change. Unlike username, it's immutable per user lifetime.
- **Unique:** "Unique identifier" explicitly stated; no collisions.
- **64-bit:** Telegram user IDs are 64-bit signed integers (fits in JavaScript BigInt, Python int, most languages). No overflow concern for typical group sizes.

Source: core.telegram.org/bots/api#message, #user

---

## Q3: Anonymous group admins / channel senders — what about `from` then?

**Answer: `from` absent OR fake; `sender_chat` present instead.**

- **Anonymous admin:** Message has `from` = fake user (backward-compat fake), `sender_chat` = supergroup Chat object.
- **Channel message:** `from` = may be empty or fake, `sender_chat` = channel Chat object.
- **Key point:** "For backward compatibility, the field _from_ contains a fake sender user in non-channel chats" when origin is a chat, not a user.
- **GroupAnonymousBot (id 1087968824):** Not the sender in modern Bot API; instead `sender_chat.id` gives actual group id.

Source: core.telegram.org/bots/api#message (fields: from, sender_chat)

---

## Q4: Can bot reliably get user_id from group messages WITHOUT username?

**Answer: YES. Always.**

- **From normal group member:** `from.id` present unconditionally.
- **Privacy mode caveat:** Bot must be admin to see all messages. But if bot processes a message it receives, `from.id` is always populated.
- **No privacy issue for access gating:** Forwarding bot receives incoming messages; each has `from.id` regardless of privacy mode state.

Source: core.telegram.org/bots/api#message

---

## Q5: Practical recommendation: gating by user_id vs username?

**Use user_id. It is the robust choice.**

Username gating fails for users without @username and breaks when users change @username. User_id is immutable, always present, unique, and 64-bit safe. For a group-forwarding bot's per-sender allowlist, gate by `from.id` (or `sender_chat.id` for anonymous admins/channel forwards). Store allowlist as `{user_id → allow_yes/no}`. This handles all sender types: normal members, channel forwards, anonymous admins. No username dependency.

---

## Unresolved questions

None. All 5 questions answered by core.telegram.org/bots/api docs.
