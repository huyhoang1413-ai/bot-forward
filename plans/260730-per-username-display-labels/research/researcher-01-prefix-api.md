# Telegram Bot API Research: Prepending Sender Attribution Labels

## Executive Summary

To prepend "[Doby] " labels to forwarded messages, use TWO approaches:
- **Media with captions**: `copy_message(caption=prefix+orig, caption_entities=shifted)`
- **Text messages**: `send_message(text=prefix+orig, entities=shifted)`
- **No caption media**: Copy as-is or precede with a separate text-only label message

Core constraint: **offsets in `caption_entities` and `entities` are UTF-16 code units**. When prepending, shift all existing entity offsets by the UTF-16 length of the prefix.

---

## Findings by Question

### 1. `copy_message` Caption Override Behavior

**YES**, `copy_message` accepts `caption` and `caption_entities` parameters.

- **Caption override**: Passing `caption` parameter REPLACES the original message's caption entirely
- **Add to media without caption**: YES, can add a caption to media that originally had none
- **Does NOT affect text messages**: `copy_message` copies the raw `text` field of text messages verbatim; the `caption` parameter only applies to media objects (photo, video, document, audio, animation, voice)
- **Media types supporting captions** (per Message schema):
  - Animation, Audio, Document, Live Photo, Paid Media, Photo, Video, Voice Message
- **Media types with NO caption** (cannot carry prefix):
  - Sticker, Poll, Dice, Location, Contact, Venue, Video Note

**Source**: [Telegram Bot API](https://core.telegram.org/bots/api)

---

### 2. Text Message Prefix via Entity Shift

For text messages, `copy_message` CANNOT prepend to the text body. **Must use `send_message`**.

**Offset encoding**: MessageEntity offsets and lengths are in **UTF-16 code units** (confirmed in API docs).

**ASCII prefix shift calculation**:
- Prefix: `"[Doby] "` = 7 ASCII characters = 7 UTF-16 code units
- Add 7 to every existing entity's `offset` field
- Keep `length` unchanged
- Example: entity at offset 0, length 5 → becomes offset 7, length 5

**UTF-16 caveats**:
- Emoji (U+1F300 and above) = 2 UTF-16 code units each
- BMP chars (most Latin/Cyrillic) = 1 UTF-16 code unit
- **Recommendation**: Avoid emoji in prefix to prevent miscalculation. Stick to ASCII `"[Doby] "`.

**Source**: [Telegram Bot API — MessageEntity](https://core.telegram.org/bots/api#messageentity)

---

### 3. Caption Entity Shift (Media with Captions)

Yes, `caption_entities` offsets are **UTF-16 code units** and must be shifted identically to text entities.

```python
# Pseudocode
prefix = "[Doby] "
prefix_utf16_len = 7  # len("[Doby] ") in UTF-16 units

shifted_entities = []
for entity in original_caption_entities:
    entity['offset'] += prefix_utf16_len
    shifted_entities.append(entity)

bot.copy_message(
    chat_id=dst_chat,
    from_chat_id=src_chat,
    message_id=msg_id,
    caption=prefix + original_caption,
    caption_entities=shifted_entities
)
```

**Source**: [Telegram Bot API](https://core.telegram.org/bots/api)

---

### 4. Message Types Without Caption or Text

**Cannot embed prefix.** Options:

| Type | Support | Recommendation |
|------|---------|-----------------|
| Sticker | None | Copy as-is OR precede with `send_message("[Doby] sticker")` |
| Poll | None | Copy as-is (poll text is immutable) |
| Dice | None | Copy as-is |
| Location | None | Copy as-is |
| Contact | None | Copy as-is |
| Venue | None | Copy as-is |
| Video Note | None | Copy as-is |

**Pattern**: For media without captions, send a separate small `send_message("[Doby]")` **immediately before** the media copy in the same forwarding batch.

---

### 5. python-telegram-bot v21 Method Signatures

**`Bot.copy_message()` relevant params**:
```python
copy_message(
    chat_id,
    from_chat_id,
    message_id,
    caption=None,                    # Optional: str
    caption_entities=None,           # Optional: list of dict | MessageEntity objects
    parse_mode=None,                 # Optional: 'HTML' | 'Markdown'
    show_caption_above_media=False,  # Optional: bool
    allow_paid_broadcast=False,      # Optional: bool
    ...
)
```

**`Bot.send_message()` relevant params**:
```python
send_message(
    chat_id,
    text,                            # Required: str
    entities=None,                   # Optional: list of dict | MessageEntity objects
    parse_mode=None,                 # Optional: 'HTML' | 'Markdown'
    ...
)
```

**Raw dict input**: Our webhook delivers raw JSON dicts (e.g., `message['text']`, `message['entities']`). These entity dicts can be passed **directly** to `copy_message()` and `send_message()` — the library auto-converts to MessageEntity objects.

**Shift implementation** (working with raw dicts):
```python
# Incoming from webhook
original_entities = message.get('entities', [])

# Shift offsets
prefix = "[Doby] "
for entity in original_entities:
    entity['offset'] += len(prefix)  # Assume ASCII-only prefix = UTF-16 length

# Pass directly
bot.send_message(
    chat_id=dst_id,
    text=prefix + message['text'],
    entities=original_entities  # Dicts OK; library converts
)
```

**Source**: python-telegram-bot v21 documentation (implied from stable Bot API)

---

### 6. parse_mode + entities Interaction

**NO**, cannot pass both `parse_mode` AND `entities` simultaneously. API enforces mutual exclusion.

**Correct pattern**:
- **Either**: `send_message(text=..., parse_mode='HTML')` — let parser handle entities
- **Or**: `send_message(text=..., entities=[...])` — pass explicit entities only
- **NOT**: `send_message(text=..., parse_mode='HTML', entities=[...])` ❌

Since we shift existing entities, **always use the `entities` parameter approach**. Never mix `parse_mode` with entity shifting.

---

## Implementation Checklist

- [ ] Text messages: use `send_message()` with shifted entities
- [ ] Media with captions: use `copy_message()` with shifted `caption_entities`
- [ ] Media without captions: copy as-is, optionally precede with label-only `send_message()`
- [ ] Prefix: ASCII only (e.g., "[Doby] "); calculate UTF-16 shift as `len(prefix)` in bytes for ASCII
- [ ] Entity dicts: pass raw webhook dicts directly; library auto-converts
- [ ] Never mix `parse_mode` + `entities`

---

## Unresolved Questions

1. Does python-telegram-bot v21 expose a utility to compute UTF-16 length for non-ASCII strings, or must we compute manually?
2. Exact edge case: if a message has BOTH `caption` (media) and inline entities in a related text field, how does `copy_message` behave? (Likely caption_entities only affect caption.)
