# Telegram Bot API: Forum Topic Semantics (Incoming)

**Research Date:** 2025-10-19  
**Sources:** [Telegram Bot API](https://core.telegram.org/bots/api#message), [python-telegram-bot docs](https://docs.python-telegram-bot.org/en/stable/telegram.message.html)

## 1. Topic Identification Fields

### Fields Present in Incoming Message

| Field | Type | Semantics |
|-------|------|-----------|
| `message_thread_id` | int \| None | "Unique identifier of a message thread or forum topic to which the message belongs; for supergroups and private chats only" |
| `is_topic_message` | bool \| None | "True, if the message is sent to a topic in a forum supergroup or a private chat with the bot" |

Both added in python-telegram-bot v20.0 (Bot API v7.0).

### Presence Rules (Inferred from API Semantics)

| Scenario | `message_thread_id` | `is_topic_message` | Notes |
|----------|--------------------|--------------------|-------|
| Message in forum topic (non-General) | Integer ≥ 1 | `True` | Standard topic; uniquely identifies topic per chat |
| Message in **General** topic (forum) | `1` (or unset) | `True` **or** None | **CRITICAL:** API docs unclear—some implementations report `message_thread_id=1`; others omit it. General topic may be `None` or `1` |
| Message in normal (non-forum) supergroup | None | None | No topic context |
| Reply in supergroup (threaded, not forum) | Integer | `False` **or** None | **RISK:** `message_thread_id` can appear for non-forum replies; keying on it alone causes false positives |
| Direct reply inside topic (reply_to_message) | Integer (same as parent) | `True` | Inherits parent's thread context |
| Private chat with bot | None | `True` **or** None | Ambiguous: bot API says "private chat with the bot" but bots rarely see private messages in forums |

**Recommended Routing Key:**
```python
topic_id = message.message_thread_id if message.is_topic_message else None
```
This **requires both conditions**:
- `is_topic_message == True` to confirm forum context
- `message_thread_id` as the stable topic identifier
- Treat `None` as "General / whole chat" for routing

## 2. General Topic Representation

**Bot API Status:** Undefined in official docs.

**Observations:**
- No explicit `ForumTopic` object with ID for General topic
- General topic events use service messages: `GeneralForumTopicHidden`, `GeneralForumTopicUnhidden` (not `ForumTopicEdited`)
- Topic names, icons, emoji belong to `ForumTopic` objects; General likely has no mutable identity
- **Likely convention:** General topic = `message_thread_id == 1` OR omitted (`None`) when `is_topic_message == True`

**For Configuration/Admin Commands:**
If `/chatid` is run in General topic:
- May receive `message.message_thread_id = 1` and `is_topic_message = True`
- Or `message_thread_id = None` with `is_topic_message = True`
- **Recommend:** Bot should check both and normalize to `topic_id = 1` for General

## 3. Service Messages

### Forum Topic Events

Arrive as `message` objects with these fields set:

| Event | Field Name | Present? | `message_thread_id` | Notes |
|-------|------------|----------|--------------------|-|
| Topic created | `forum_topic_created` | Yes | Topic ID | Posted to the topic itself (no notification in General) |
| Topic edited | `forum_topic_edited` | Yes | Topic ID | Edit, name, or icon change |
| Topic closed | `forum_topic_closed` | Yes | Topic ID | Topic becomes read-only |
| Topic reopened | `forum_topic_reopened` | Yes | Topic ID | Topic writable again |
| General hidden | `general_forum_topic_hidden` | Yes | 1 (or None) | General topic becomes hidden (archived) |
| General unhidden | `general_forum_topic_unhidden` | Yes | 1 (or None) | General topic visible again |

**Forwarding Implication:**
- These are **service messages**, not user content—bots should **ignore for forwarding**
- Each carries the topic context; safe to filter by `message_thread_id`

## 4. Admin `/chatid` Command in Topics

When admin runs `/chatid` inside a topic:

**Expected fields on the command message itself:**
```json
{
  "message_id": 123,
  "chat": { "id": -100123456, "type": "supergroup" },
  "message_thread_id": <topic_id>,
  "is_topic_message": true,
  "text": "/chatid"
}
```

**Recommended bot response:**
```
Chat ID: -100123456
Topic ID: <message.message_thread_id>
Topic Name: <from chat.get_forum_topic_info() or saved config>
```

Command message itself carries both identifiers; no API call needed unless displaying topic name.

## 5. Edge Cases

### Edited Messages in Topics
- Arrive via `update["edited_message"]` with **identical** `message_thread_id` and `is_topic_message` as original
- No change to routing key

### Anonymous Admins / Channel Posts in Forums
- Channel posts forwarded to a forum topic: carry `message_thread_id`, `is_topic_message = True`
- No `from_user` field; `is_automatic_forward = True` if forwarded from linked channel
- Still routable by topic; `from_user` check not reliable for these

### Replies to Messages Across Topics
- Reply to message in Topic A, posted from Topic B: carries **Topic B's** `message_thread_id`
- (Bot API does not allow replies across topics in forums)

## Unresolved Questions

1. **General topic ID exact value:** Does General topic always have `message_thread_id = 1`, or is it sometimes omitted entirely? Needs test on live bot to confirm.
2. **Private chat ambiguity:** Does `is_topic_message = True` ever occur in actual private bot messages, or is it reserved for channel/group forwarding?
3. **Linked channel replies:** When a forum topic has a linked discussion channel, do replies in the channel appear in the forum with the topic's `message_thread_id`?

## Summary Table: Stable Routing Logic

```python
def get_topic_id(message_dict):
    """Extract stable topic key for forwarding routing."""
    is_topic = message_dict.get("is_topic_message", False)
    thread_id = message_dict.get("message_thread_id")
    
    if is_topic and thread_id is not None:
        return thread_id  # e.g., 123 (topic) or 1 (General)
    elif is_topic and thread_id is None:
        return 1  # Assume General if field omitted
    else:
        return None  # No topic context (regular supergroup/private)
```

**Field URLs:**
- Message.message_thread_id: https://core.telegram.org/bots/api#message
- Message.is_topic_message: https://core.telegram.org/bots/api#message
- Forum service messages: https://core.telegram.org/bots/api#forumtopicclosed
- python-telegram-bot Message: https://docs.python-telegram-bot.org/en/stable/telegram.message.html
