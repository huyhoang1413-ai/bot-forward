# Phase 02 — Core Forwarding Engine & Commands

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-scaffold-and-config.md) (config + logging)
- Research: [researcher-01](research/researcher-01-libraries-api.md) (copy vs forward, media, rate limits), [researcher-02](research/researcher-02-architecture-ops.md) (loop guard, commands)
- Docs: copyMessage https://core.telegram.org/bots/api#copymessage ; PTB handlers https://docs.python-telegram-bot.org/

## Overview
- **Date**: 2026-07-22
- **Description**: Build the routing table, the message handler that copies each incoming group message to all bridged destinations, bidirectional loop guard, and utility commands (`/start`, `/chatid`, `/status`). Wire everything in `__main__.py` with long polling + rate limiter.
- **Priority**: High (core deliverable)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Bridge is stateless → no DB. For message X in group A, copy to every group paired with A.
- **Loop guard**: ignore updates whose sender is our own bot (`update.effective_user.id == bot.id`) — this stops the bot's own copies from being re-bridged and prevents infinite A↔B loops. Human messages still bridge both directions.
- `copy_message` handles all content types by `(from_chat_id, message_id)` — no per-type branching (KISS). Album grouping lost (documented limit; deferred).
- Use `Message.copy(chat_id=dest)` per destination; PTB `AIORateLimiter` auto-honors 429 `retry_after`.
- Privacy mode must be OFF or bot must be admin, else group messages never reach the handler.

## Requirements
- Handler triggers on all non-command messages in known source chats (`filters.ChatType.GROUPS & ~filters.COMMAND`, or filter by configured chat ids).
- Skip messages from the bot itself and any message whose `effective_chat.id` is not a configured source.
- `/chatid` replies with `update.effective_chat.id` (works in group & private) — the onboarding tool to discover ids.
- `/status` replies with bot uptime + number of active bridges/routes.
- `/start` short help text (Vietnamese user-facing text OK; keep code English).

## Architecture
```
bot/
├── router.py     # RouteTable.from_bridges(bridges) -> {source_id: [dest_ids]}
│                 #   .destinations(source_id) -> list[int]
├── handlers.py   # forward_handler, cmd_start, cmd_chatid, cmd_status
└── __main__.py   # build Application(token, AIORateLimiter), add handlers, run_polling
```
`router.py`:
- `RouteTable`: dict `source_id -> list[dest_id]`. `from_bridges`: for `[A,B]` add B to A's list and A to B's list. De-dup destinations.

`handlers.py` (pseudocode):
```python
async def forward_handler(update, context):
    msg = update.effective_message
    src = update.effective_chat.id
    if update.effective_user and update.effective_user.id == context.bot.id:
        return                              # loop guard
    dests = context.bot_data["routes"].destinations(src)
    for dest in dests:
        try:
            await msg.copy(chat_id=dest)    # clean copy, all types
        except Exception as e:
            logging.error("copy %s->%s failed: %s", src, dest, e)
```
`__main__.py`: `Application.builder().token(cfg.token).rate_limiter(AIORateLimiter()).build()`; store `RouteTable` in `application.bot_data["routes"]`; register command + message handlers; `app.run_polling(allowed_updates=Update.ALL_TYPES)`.

## Related code files
- `bot/router.py` (new)
- `bot/handlers.py` (new)
- `bot/__main__.py` (replace Phase-01 stub)

## Implementation Steps
1. Implement `RouteTable` + `from_bridges` in `router.py`.
2. Implement `forward_handler` with loop guard + per-dest copy + error logging.
3. Implement `/start`, `/chatid`, `/status` command handlers.
4. Build `Application` in `__main__.py` with `AIORateLimiter`, register handlers, store routes in `bot_data`, `run_polling`.
5. Manual smoke test: create 2 test groups, add bot as admin to both, add pair to `routes.yaml`, run, send text/photo/file in A → appears in B and vice-versa; verify no echo loop.

## Todo list
- [ ] router.py RouteTable + from_bridges (+ dedup)
- [ ] forward_handler with loop guard
- [ ] /start /chatid /status commands
- [ ] __main__ Application wiring + run_polling
- [ ] real 2-group smoke test (text, photo, document, sticker)

## Success Criteria
- Message sent in group A is copied to group B and vice-versa (bidirectional) for text, photo, video, document, sticker.
- No infinite loop / no echo of the bot's own copies.
- `/chatid` returns the correct chat id; `/status` shows uptime + route count.
- Copy failure to one destination logs an error but does not crash the bot.

## Risk Assessment
- **Loop risk** (medium) if guard wrong → mitigated by skipping bot's own messages; verified in smoke test.
- **Privacy mode** (medium): if not admin / privacy on, no messages arrive → document "make bot admin" in README.
- **Album split** (low): multi-photo posts arrive separate → documented limitation.
- **Rate limit** (low): 2-group traffic small; `AIORateLimiter` covers bursts.

## Security Considerations
- Bot only copies between explicitly configured chats; unknown chats ignored (no data leak).
- No command exposes the token or config file contents.
- Grant bot minimal group rights (send messages); no delete/ban needed.

## Next steps
Proceed to [Phase 03](phase-03-testing-deployment-docs.md) — automated tests, deployment (Windows/VPS/Docker), README.
