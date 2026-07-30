# Phase 02 — Bot Lifecycle (Validate, Add/Remove, Webhook Registration)

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-skeleton-auth-db.md) (models, crypto, auth)
- Research: [researcher-01](research/researcher-01-multibot-runtime.md) (getMe, setWebhook/deleteWebhook, secret_token)
- Docs: setWebhook https://core.telegram.org/bots/api#setwebhook ; getMe https://core.telegram.org/bots/api#getme

## Overview
- **Date**: 2026-07-27
- **Description**: Service layer to register a bot from a pasted token (validate → encrypt+store → set webhook) and to remove it (delete webhook → mark/delete). Re-sync webhooks on server startup.
- **Priority**: High (core value: "paste token → works")
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- `Bot(token).get_me()` validates a token and yields `telegram_bot_id` + `username`. Invalid/revoked → exception → reject before storing.
- `setWebhook(url=f"{PUBLIC_URL}/webhook/{bot_id}", secret_token=..., allowed_updates=[...])` activates delivery; **idempotent** (re-registering is safe).
- Per-bot random `webhook_secret` verified later via `X-Telegram-Bot-Api-Secret-Token`.
- On startup, iterate active bots and re-`setWebhook` (URL/secret may have changed, or Telegram dropped it). No restart needed to add/remove at runtime.
- `bot_id` in the URL is the DB id (opaque), not the token — token never in URL.

## Requirements
- `telegram.py` service:
  - `async validate_token(token) -> (telegram_bot_id, username)` (raises on invalid).
  - `async register_webhook(bot_id, token, secret)` → setWebhook.
  - `async unregister_webhook(token)` → deleteWebhook(drop_pending_updates=True).
- `services.py` (or in `telegram.py`):
  - `async add_bot(token) -> Bot`: validate, dedup by telegram_bot_id, encrypt token, generate secret, insert, register_webhook.
  - `async remove_bot(bot_id)`: load, decrypt token, unregister_webhook, delete row (+ its routes).
  - `async resync_all_webhooks()`: called from FastAPI lifespan startup.
- Handle Telegram `allowed_updates=["message","edited_message"]` (message + commands).

## Architecture
```
webapp/app/
├── telegram.py    # thin async wrappers over PTB Bot: validate, set/delete webhook
├── services.py    # add_bot / remove_bot / resync_all_webhooks (DB + telegram)
```
Flow (add):
```
POST token -> validate_token(getMe) -> exists? reject dup
           -> secret = token_urlsafe(); enc = encrypt_token(token)
           -> insert Bot(...) -> register_webhook(bot.id, token, secret)
           -> return Bot
```
Startup: `lifespan` → `resync_all_webhooks()` (best-effort; log failures, mark bot `invalid` if getMe fails).

## Related code files
- `webapp/app/telegram.py`, `webapp/app/services.py` (new)
- `webapp/app/main.py` (add lifespan calling resync)
- Uses `models.Bot`, `crypto`, `config.PUBLIC_URL`.

## Implementation Steps
1. `telegram.py`: implement `validate_token`, `register_webhook`, `unregister_webhook` using `telegram.Bot`.
2. `services.add_bot`: validation, dedup, encrypt, secret gen, insert, register. Return created bot or raise typed errors (InvalidToken, DuplicateBot).
3. `services.remove_bot`: unregister + cascade delete routes + delete bot.
4. `services.resync_all_webhooks`: loop active bots, re-register; mark `invalid` on getMe failure.
5. Wire `resync_all_webhooks` into `main.py` lifespan startup.

## Todo list
- [ ] telegram.py validate/register/unregister
- [ ] services.add_bot (validate+encrypt+store+setWebhook, dedup)
- [ ] services.remove_bot (deleteWebhook + cascade)
- [ ] services.resync_all_webhooks + lifespan hook
- [ ] typed errors surfaced to UI layer

## Success Criteria
- Pasting a **valid** token stores an encrypted bot row and Telegram `getWebhookInfo` shows the correct URL.
- Pasting an **invalid** token returns a clear error, stores nothing.
- Duplicate token (same telegram_bot_id) is rejected.
- Removing a bot clears its webhook (getWebhookInfo empty) and deletes its routes.
- Restarting the server re-applies webhooks for all active bots.

## Risk Assessment
- **Medium**: partial failure (row inserted but setWebhook fails) → wrap in try/except, roll back insert or mark `invalid` + retry on resync.
- **Low**: Telegram transient errors → resync is best-effort with logging.

## Security Considerations
- Token decrypted only in-memory for the API calls; never logged or returned to the browser.
- `webhook_secret` random per bot (≥32 chars), stored server-side only.
- Reject tokens over a max length; strip whitespace.

## Next steps
Proceed to [Phase 03](phase-03-webhook-forwarding.md) — receive updates on the registered webhooks and forward.
