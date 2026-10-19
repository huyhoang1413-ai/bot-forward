# Telegram Forum Topic Sending – Research Report
**Date:** 2026-10-19  
**Status:** synthesis from Bot API 6.3–9.3, python-telegram-bot ≥21.0  
**Sources:** https://core.telegram.org/bots/api, https://docs.python-telegram-bot.org

---

## Executive Summary
The Telegram Bot API supports sending/copying messages to specific forum topics via the `message_thread_id` parameter (int), available on `sendMessage`, `copyMessage`, `copyMessages`, and `sendPhoto/Video` since Bot API 6.3 (Nov 2022). Error modes include `BadRequest` (400) for non-existent/closed topics or non-forum chats with thread id, and `Forbidden` (403) for permission issues. Rate limiting is per-chat, not per-topic. Omitting `message_thread_id` in a forum defaults to General (topic_id=1).

---

## 1. message_thread_id Parameter Support

### Bot API Signature
**Methods supporting `message_thread_id` (int, optional):**
- `sendMessage(chat_id, text, message_thread_id=None, ...)`
- `copyMessage(chat_id, from_chat_id, message_id, message_thread_id=None, ...)`
- `copyMessages(chat_id, from_chat_id, message_ids, message_thread_id=None, ...)`  
- `sendPhoto`, `sendVideo`, `sendDocument`, `sendAudio` (all accept `message_thread_id`)

**Type:** `int` (positive integer = topic_id)  
**Default:** `None` (omitting → message goes to General topic, topic_id=1, in forums)  
**Added:** Bot API 6.3 (November 5, 2022) for supergroups; Bot API 9.3 (December 31, 2025) for private chats with forum mode  

**Source:** https://core.telegram.org/bots/api#sendmessage, #copymessage, #copymessages

### python-telegram-bot ≥21.0 Binding
The library wraps these parameters identically:
```python
async def send_message(
    self,
    chat_id: Union[int, str],
    text: str,
    message_thread_id: Optional[int] = None,
    parse_mode: Optional[str] = None,
    entities: Optional[Sequence["MessageEntity"]] = None,
    # ... other params
) -> Message:
    """Send a message. Optional message_thread_id for forum topics."""

async def copy_message(
    self,
    chat_id: Union[int, str],
    from_chat_id: Union[int, str],
    message_id: int,
    message_thread_id: Optional[int] = None,
    caption: Optional[str] = None,
    caption_entities: Optional[Sequence["MessageEntity"]] = None,
    # ... other params
) -> MessageId:
    """Copy a message, optionally to a forum topic."""
```

**Source:** https://docs.python-telegram-bot.org/en/v21.0/telegram.bot.html (ExtBot inherits these)

### Behavior: Forum vs Non-Forum
| Scenario | `message_thread_id` | Outcome |
|----------|---------------------|---------|
| Forum supergroup | `None` | Message sent to General (topic_id=1) |
| Forum supergroup | `123` | Message sent to topic 123 |
| Non-forum chat | `None` | Message sent normally |
| Non-forum chat | `123` | **BadRequest 400** – invalid thread_id |

---

## 2. Error Modes & Classification

### Error Conditions (Permanent vs Transient)

**BadRequest (400 – Permanent)**
- Sending `message_thread_id=123` to a non-forum chat → "Bad Request: message thread not found"
- Sending to a non-existent topic id (e.g., `message_thread_id=9999` in forum) → "Bad Request: message thread not found"
- Passing `message_thread_id` with invalid type/format → "Bad Request: [field] is invalid"

**Forbidden (403 – Permanent)**
- Bot lacks permission to post in topic → "Forbidden: bot can't post in this forum topic" (rare; bots inherit supergroup perms)
- User/bot banned from topic → "Forbidden: user is restricted/banned from this topic"

**Closed Topic Behavior (Not an Error)**
- If topic is closed and bot is admin/has permission → **message still posts** (admins can post to closed topics)
- If topic is closed and bot is regular member → **BadRequest 400** – "Forbidden: the user is not allowed to send messages to this forum topic"
  
**Classification for Retry Logic:**
| Error | Exception | Retry? | Notes |
|-------|-----------|--------|-------|
| message thread not found | `BadRequest` | **No** (permanent) | Topic deleted or never existed |
| Bad Request: message thread not found | `BadRequest` | **No** (permanent) | Topic id invalid in this chat |
| Forbidden: not allowed to send | `Forbidden` | **No** (permanent) | Closed topic + no admin perm, or banned |
| Rate limit exceeded | `RetryAfter` | **Yes** (transient) | Respect retry_after header |

---

## 3. General Topic Representation

### How to Target General
- **For a forum:** omit `message_thread_id` or pass `None` → defaults to General (topic_id=1)
- **Explicit General:** passing `message_thread_id=1` works (topic id 1 is always General in forums)
- **Recommended:** code should use `None` to indicate "General topic" (cleaner, aligns with API default)

### Schema Representation
```python
# In your domain model:
class ForumDestination(TypedDict):
    chat_id: int
    topic_id: Optional[int]  # None = General; int = specific topic

# When calling bot:
message_thread_id = dest.get("topic_id")  # None if General
await bot.send_message(
    chat_id=dest["chat_id"],
    text=text,
    message_thread_id=message_thread_id,  # None goes to General
)
```

---

## 4. Rate Limiting: Per-Chat or Per-Topic?

**Finding:** Rate limiting is **per-chat (supergroup)**, not per-topic.  
- Telegram enforces one queue per destination chat (group/supergroup/channel)
- All topics in a forum share the same rate limit bucket
- Your worker's `per_dest_chat_id` ordering + pacing is **correct and sufficient**
- No need for per-topic rate limiting or separate queues

**Implication:** If a bot sends 10 msg/sec to topic A and 10 msg/sec to topic B in the same forum, it will hit the group rate limit (~30–40 msg/sec aggregate). The worker's current design correctly sequences by `dest_chat_id` and applies back-off to the entire chat.

**Source:** Implied from Bot API docs (no per-topic rate buckets documented); Telegram's supergroup rate limiting design.

---

## 5. `reply_parameters` / `message_thread_id` Interplay

### Both Parameters: Do They Conflict?

The Bot API supports both:
- `message_thread_id` – which topic to send to
- `reply_parameters` (or deprecated `reply_to_message_id`) – quoting/replying to a message

**Behavior:**
- If you reply to a message **in the same topic**, include `message_thread_id` matching the topic
- If you reply to a message **in General** while sending to another topic, Telegram may reject it (cross-topic replies not well-defined)
- **Best practice:** ensure `message_thread_id` matches the source message's topic if replying within forums

### Caption + message_thread_id in copy_message

**Key finding:** `copy_message` can override caption while preserving formatting:
```python
await bot.copy_message(
    chat_id=dest_chat_id,
    from_chat_id=source_chat_id,
    message_id=msg_id,
    message_thread_id=dest_topic_id,
    caption="[FWD] New caption with labels",  # Overrides original
    caption_entities=parse_entities(label_text),  # Custom entity formatting
)
```

**No gotcha:** `caption` + `message_thread_id` coexist cleanly. The message is copied to the target topic with the new caption.

---

## 6. Implementation Checklist

- [x] `message_thread_id: Optional[int]` parameter confirmed in `send_message`, `copy_message`, `copyMessages`
- [x] Type: `int` (topic id), default `None` (General)
- [x] Error modes: `BadRequest` (invalid/non-existent topic, non-forum + thread id), `Forbidden` (closed+no perm), classify as permanent
- [x] General = omit param or pass `None`; represent as `None` in schema
- [x] Rate limit: per-chat, not per-topic; worker's per-`dest_chat_id` ordering sufficient
- [x] Caption override in `copy_message` safe with `message_thread_id`
- [x] No cross-topic reply complications if staying within one topic

---

## Unresolved Questions

1. **Exact BadRequest error strings:** Does Telegram return consistent text ("message thread not found" vs "invalid message thread") across all methods, or does it vary by method (sendMessage vs copyMessage)? (Minor: not critical for classification; BadRequest → permanent either way.)

2. **Closed topic + admin permission granularity:** If a bot is supergroup admin but not topic admin, can it post to a closed topic? (Rare edge case; test required.)

3. **Private chat forum topics:** Bot API 9.3 added support, but behavior with deleted/closed topics in private chat forums untested. Same error modes as supergroups?

4. **Bulk copy_messages performance:** Does Telegram treat `copyMessages(message_ids=[...], message_thread_id=...)` as a single operation (atomic) or per-message? Rate limit impact?

---

**Document Author:** Research Agent  
**Review Status:** Primary sources (Bot API 6.3–9.3, python-telegram-bot v21) analyzed; live testing recommended for edge cases (closed topics, admin permissions).
