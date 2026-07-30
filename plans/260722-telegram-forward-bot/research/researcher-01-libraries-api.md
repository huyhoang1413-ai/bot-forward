# Research 01 — Telegram Libraries & Forwarding API

## 1. Bot API vs MTProto (userbot)
- **Bot API** (HTTPS, via @BotFather token): a bot can only see messages in chats it is a **member of**. To forward group→group the bot must be **added to BOTH** source and destination groups.
- **Privacy mode**: by default a group bot only receives commands (`/cmd`) & replies/mentions, NOT all messages. Must **disable privacy mode** via @BotFather (`/setprivacy` → Disable) OR make the bot an **admin** (admins always receive all messages regardless of privacy mode). → For a forwarder, make bot **admin** in source group. [https://core.telegram.org/bots/features#privacy-mode]
- **MTProto/userbot** (Telethon/Pyrogram, uses a user account + api_id/api_hash): can read ANY chat the account is in, no "add bot" needed. More power but **ToS risk** (account bans for automation). User chose Bot API → out of scope.

## 2. Python libraries
| Lib | Async | Maturity | Notes |
|-----|-------|----------|-------|
| **python-telegram-bot (PTB) v21+** | asyncio | Very mature, huge docs | Best general-purpose Bot API wrapper. Recommended. |
| **aiogram v3** | asyncio-native | Mature, popular | Great too; router/filter design. Also solid choice. |
| Telethon / Pyrogram | asyncio | Mature | MTProto (userbot) — not needed for Bot API. |

**Recommendation: python-telegram-bot v21+** — cleanest Bot API coverage, excellent docs, `Application` + handlers, built-in `copy_message`, media-group support, rate-limit helper (`AIORateLimiter`). [https://docs.python-telegram-bot.org/]

## 3. forward_message vs copy_message
- `forward_message` / `Message.forward()`: shows **"Forwarded from <source>"** header (attribution, links back). Preserves origin. Can leak source group name.
- `copy_message` / `Message.copy()`: sends a **clean copy** (no "Forwarded from"), like the bot authored it. Keeps caption/media/keyboard. Best when you want a seamless bridge. [https://core.telegram.org/bots/api#copymessage]
- User picked "forward cơ bản mọi loại" → **`copy_message` recommended** for a clean bridge (no forwarded-tag clutter), but `forward_message` is a one-line swap if attribution wanted.

## 4. Message types & media groups
- `copy_message`/`forward_message` handle **text, photo, video, document, audio, voice, sticker, animation, location, contact, poll** transparently by message_id — no per-type code needed. ✅ simplest.
- **Media groups (albums)**: a multi-photo/video album arrives as **multiple separate Update messages** sharing a `media_group_id`. Copying each individually → destination shows them as separate messages, NOT a grouped album. To preserve album grouping must buffer messages by `media_group_id` (short debounce ~1s) then re-send via `send_media_group`. **Known limitation** — flag as optional enhancement (YAGNI for v1). [https://core.telegram.org/bots/api#sendmediagroup]
- `copy_message` cannot copy polls/some service messages in a group send; individual copy is fine.

## 5. Rate limits
- Bot API soft limits: **~30 messages/second** overall; **~1 message/second to the same chat** (bursts to ~20/min per group tolerated). Exceeding → HTTP 429 with `retry_after`. [https://core.telegram.org/bots/faq#my-bot-is-hitting-limits-how-do-i-avoid-this]
- Mitigation: respect `retry_after` on 429 (PTB does with `AIORateLimiter`), avoid tight loops, add small queue/delay for one-to-many fan-out. Bridge (2 groups) traffic is low → low risk.

## 6. Long polling vs webhooks
- **Long polling** (`Application.run_polling()`): bot pulls updates; NO public URL/HTTPS/port needed. Ideal for local PC / simple VPS. Easiest. ✅ Recommended for this project.
- **Webhooks**: Telegram pushes to your HTTPS endpoint; needs public domain + TLS + open port. Better for high scale / serverless. Overkill here.

## Unresolved questions
- Preserve album grouping in v1 or defer? (recommend defer — copy each message; note limitation).
- Use `copy_message` (clean) vs `forward_message` (attribution)? Recommend copy; confirm with user.
- Does user need reply-threading preserved across the bridge? (copy loses reply linkage unless mapped — likely YAGNI).
