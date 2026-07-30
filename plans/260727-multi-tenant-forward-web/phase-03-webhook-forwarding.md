# Phase 03 — Webhook Receiver & Shared Forwarding Dispatcher

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-skeleton-auth-db.md), [Phase 02](phase-02-bot-lifecycle.md)
- Research: [researcher-01](research/researcher-01-multibot-runtime.md) (multiplexing, secret header, copy_message, rate limits)
- Docs: copyMessage https://core.telegram.org/bots/api#copymessage

## Overview
- **Date**: 2026-07-27
- **Description**: The `POST /webhook/{bot_id}` endpoint that verifies the secret header, dispatches each update to the shared forwarding logic (copy_message across configured routes), and handles the `/chatid` `/start` commands. This is where the forwarding actually happens for every bot.
- **Priority**: High (core deliverable)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- One endpoint multiplexes all bots via `{bot_id}`. Look up bot + routes from DB, decrypt token, act. **Cache `Bot` instances** in-memory keyed by bot_id to avoid rebuilding per update.
- **Verify** `X-Telegram-Bot-Api-Secret-Token` header == bot's `webhook_secret`; reject otherwise (blocks spoofed posts).
- **Ack fast**: Telegram sends updates serially per bot and waits for HTTP 200. Return 200 quickly; do copy work inline (small) or via `asyncio` task. For MVP, inline is fine at low volume.
- **Loop guard**: skip updates whose sender is the bot itself (`message.from.id == telegram_bot_id`) → prevents A↔B loops (same rule as single-bot version).
- `/chatid` must work here (webhook mode) so the admin can discover group ids during onboarding.
- Rate limit: `asyncio.Semaphore` to cap concurrent `copy_message` calls; honor 429 `retry_after` (PTB `Bot` + optional rate limiter).

## Requirements
- `POST /webhook/{bot_id}`: parse `Update`, verify secret, dispatch, always return `{"ok": true}` 200 (even on internal skip) to avoid Telegram retries storms; log errors.
- Dispatcher `forward_update(bot, telegram_bot_id, routes, update)`:
  - command `/chatid` → reply chat id; `/start` → short help.
  - else for each enabled route where `source_chat_id == chat.id`: `bot.copy_message(dest, source, message_id)`.
  - loop guard + per-dest error logging (don't crash).
- Bot instance + routes cache with invalidation when routes/bots change (simple: TTL or explicit clear on UI edits).

## Architecture
```
webapp/app/
├── webhook.py     # router: POST /webhook/{bot_id}
├── forwarding.py  # forward_update(...) shared logic (copy_message, commands, loop guard)
├── botcache.py    # get_bot(bot_id) -> cached telegram.Bot ; get_routes(bot_id)
```
Handler (pseudocode):
```python
@router.post("/webhook/{bot_id}")
async def webhook(bot_id: int, request: Request):
    bot_row = load_bot(bot_id)                    # 404 if missing/disabled
    if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != bot_row.webhook_secret:
        raise HTTPException(403)
    update = Update.de_json(await request.json(), get_bot(bot_id))
    try:
        await forward_update(get_bot(bot_id), bot_row.telegram_bot_id,
                             get_routes(bot_id), update)
    except Exception as e:
        logger.error("dispatch bot=%s: %s", bot_id, e)
    return {"ok": True}
```

## Related code files
- `webapp/app/webhook.py`, `webapp/app/forwarding.py`, `webapp/app/botcache.py` (new)
- Reuses forwarding idea from existing `bot/handlers.py` (`forward_handler` loop guard + copy_message).
- `main.py` includes the webhook router.

## Implementation Steps
1. `botcache.py`: memoize `Bot(decrypt_token(...))` per bot_id; `get_routes(bot_id)` from DB; `invalidate(bot_id)`.
2. `forwarding.py`: implement `forward_update` (commands + route copy + loop guard + semaphore).
3. `webhook.py`: endpoint with secret verification + fast 200 + error logging.
4. Include router in `main.py`; call cache invalidation from route/bot mutations (Phase 04 UI).
5. Local test with ngrok/Cloudflare Tunnel + a real test bot: /chatid works, message in source appears in dest.

## Todo list
- [ ] botcache.py (Bot cache + routes cache + invalidate)
- [ ] forwarding.py forward_update (copy, /chatid, /start, loop guard, semaphore)
- [ ] webhook.py endpoint + secret header verification + fast 200
- [ ] include router + invalidate on mutations
- [ ] real webhook smoke test via tunnel (2 groups, 1 bot)

## Success Criteria
- Real message in a configured source group is copied to the dest group through the webhook path.
- `/chatid` in a group replies with the correct id.
- Spoofed request without valid secret header → 403, no action.
- Bot's own copies are not re-forwarded (no loop) for bidirectional routes.
- A failing copy to one dest logs an error but the endpoint still returns 200.

## Risk Assessment
- **Medium**: slow inline processing could delay Telegram acks under load → offload to `asyncio.create_task` if needed; MVP inline OK.
- **Medium**: stale cache after route edits → invalidate on mutation.
- **Low**: duplicate delivery on Telegram retry → copy is idempotent-ish (may double-post rarely); acceptable for MVP, note it.

## Security Considerations
- Secret-token header verification mandatory; constant-time compare.
- `bot_id` unknown/disabled → 404 without leaking which ids exist.
- Never echo token; never trust `update` fields for auth decisions.

## Next steps
Proceed to [Phase 04](phase-04-web-ui.md) — the admin UI to drive add-bot and routes, invalidating caches on change.
