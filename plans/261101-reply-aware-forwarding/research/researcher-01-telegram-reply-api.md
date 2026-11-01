# Telegram Reply-Aware Forwarding: API Research

## 1. Reading Incoming Replies: `message.reply_to_message`

**Source:** [Telegram Bot API Message object](https://core.telegram.org/bots/api#message)
**PTB v21 Reference:** [Message class](https://docs.python-telegram-bot.org/en/v21.9/telegram.message.html)

When a message is a reply, the incoming `Update.message` object contains:
- `message.message_id` (int) — unique identifier in this chat
- `message.reply_to_message` (Message, optional) — the original message object (fully populated with nested properties)
- `message.reply_to_message.message_id` — the target message ID
- `message.reply_to_message.from_user.first_name` — sender name (for label context)
- `message.reply_to_message.text` or `.caption` — content for quote fallback

`reply_to_message` is always present if the message is a reply in the same chat. Auto-pinned messages and forwards do NOT populate `reply_to_message` (they use `forward_from_chat` / `forward_date` instead). Nested `reply_to_message.reply_to_message` is NOT populated (stops at one level).

## 2. Outgoing Reply with `ReplyParameters` (PTB v21)

**Source:** [python-telegram-bot ReplyParameters](https://docs.python-telegram-bot.org/en/v21.9/telegram.replyparameters.html)

Replace deprecated `reply_to_message_id` with `ReplyParameters`:

```python
from telegram import ReplyParameters

reply_params = ReplyParameters(
    message_id=dest_message_id,  # ID of copied/sent message in destination
    allow_sending_without_reply=True,  # Send even if target deleted
    quote="optional snippet",  # 0-1024 chars, optional
    quote_parse_mode="HTML",  # Parse mode for quote text
)

# For Bot.copy_message:
await bot.copy_message(
    chat_id=dest_chat_id,
    from_chat_id=source_chat_id,
    message_id=source_msg_id,
    reply_parameters=reply_params,
)

# For Bot.send_message (labeled text):
await bot.send_message(
    chat_id=dest_chat_id,
    text="↳ Label: " + text,
    reply_parameters=reply_params,
)
```

Constructor parameters: `message_id`, `chat_id` (optional, for cross-chat replies), `allow_sending_without_reply`, `quote`, `quote_parse_mode`, `quote_entities`, `quote_position`.

## 3. Return Values: Capturing `dest_message_id`

**Source:** [Bot.copy_message](https://docs.python-telegram-bot.org/en/v21.9/telegram.bot.html), [MessageId object](https://core.telegram.org/bots/api#messageid)

- `copy_message()` returns `MessageId` — lightweight, use `.message_id` attribute.
- `send_message()` returns full `Message` — use `.message_id` attribute.

```python
msg_id_obj = await bot.copy_message(...)  # MessageId
dest_id = msg_id_obj.message_id

msg = await bot.send_message(...)  # Message
dest_id = msg.message_id
```

Both have `.message_id` attribute; identical for destination capture.

## 4. Forum Topics + Reply Parameters: Validity & Conflicts

**Source:** [Bot API changelog](https://core.telegram.org/bots/api-changelog)

Setting both `message_thread_id` and `reply_parameters.message_id` is **valid and expected**:
- `message_thread_id` designates the destination forum topic.
- `reply_parameters.message_id` creates the reply link within that topic.

**Rule:** `allow_sending_without_reply=True` and `quote_entities` can **only** be used for replies in the same chat and forum topic. If the reply target is in a *different* topic, `allow_sending_without_reply` is ignored (forced False by Telegram). Cross-topic replies must use `allow_sending_without_reply=False`.

No conflict exists; both parameters coexist naturally for topic-aware replies.

## 5. Native Quote (`ReplyParameters.quote`): Feasibility

**Source:** [ReplyParameters](https://docs.python-telegram-bot.org/en/v21.9/telegram.replyparameters.html)

`quote` parameter (0–1024 characters post-entity parsing) allows native quoted replies. Advantages:
- Telegram UI renders with native quote bubble (familiar to users).
- Simpler than prepending "↳ ..." text.
- Supports `quote_parse_mode` (HTML, Markdown, MarkdownV2) and `quote_entities` for formatting.

**Tradeoff:** Quote is limited to 1024 chars. For longer original messages, either truncate or fall back to text prefix. Native quote is **simpler and recommended** for standard use cases.

## 6. Error Behavior: Deleted Reply Target

**Source:** [Telegram Bot API errors](https://core.telegram.org/bots/api#getting-updates), GitHub issues on BadRequest

- **Without `allow_sending_without_reply`:** BadRequest error (permanent) if `message_id` is deleted/foreign.
- **With `allow_sending_without_reply=True`:** Message is sent as a standalone message (reply link dropped), no error.

For `copy_message` with a deleted `reply_parameters.message_id`:
- Error is **BadRequest** (type: "Bad Request", code 400) — permanent, not retryable.
- With `allow_sending_without_reply=True`, copy proceeds as a non-reply.

**Recommendation:** Always use `allow_sending_without_reply=True` in production since mapped source messages may be deleted before the copy operation.

## 7. Rate Limiting & AIORateLimiter

**Source:** [python-telegram-bot AIORateLimiter](https://github.com/python-telegram-bot/python-telegram-bot)

Adding `reply_parameters` does **not** change rate-limit behavior. AIORateLimiter rate-limits by (chat_id, user_id) or per-bot. The reply link is metadata; it does not incur additional API calls or rate-limit overhead.

**Error 429:** "Too Many Requests" — includes `retry_after` seconds. Handled transparently by PTB's rate limiter with exponential backoff.

---

## Summary: Implementation Checklist

1. **Incoming:** Check `message.reply_to_message` to detect replies; extract `.message_id`.
2. **Mapping:** Store `(source_msg_id, dest_msg_id)` in a dict/DB.
3. **Outgoing:** Use `ReplyParameters(message_id=dest_id, allow_sending_without_reply=True)`.
4. **Forums:** Pass both `message_thread_id=mt` and `reply_parameters=...` without conflict.
5. **Quote:** Prefer `ReplyParameters.quote` over text prefix for UX; truncate to 1024 chars if needed.
6. **Errors:** BadRequest on deleted reply target is expected; `allow_sending_without_reply=True` mitigates.
7. **Rate limits:** No changes; AIORateLimiter handles transparently.

---

## Unresolved Questions

1. **Cross-chat reply edge case:** If destination is a different chat, does Telegram enforce same-topic rule? (Suspected: `chat_id` in ReplyParameters bypasses topic restriction.)
2. **Ephemeral messages:** Do ephemeral messages in private chats support replies/replies-to? (v21.9 docs silent; may need testing or v22+ changelog review.)
3. **Quote truncation UX:** Should we preserve quote order (prefix first 1024 chars) or summarize intelligently? (Preference unclear; recommend prefix for simplicity.)
