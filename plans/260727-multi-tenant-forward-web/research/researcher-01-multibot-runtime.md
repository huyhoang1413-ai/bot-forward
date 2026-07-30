# Multi-Tenant Telegram Bot Architecture: Webhooks & Runtime Management

## 1. Polling vs. Webhooks at Scale

**Polling (getUpdates loop):** O(N) polling loops for N bots. Each bot maintains separate long-polling connection consuming RAM/CPU, blocking event loop. Unsuitable for 10+ bots on single VPS.

**Webhooks (setWebhook):** Single HTTPS endpoint. Telegram pushes updates via POST to `/webhook/{bot_id}` or similar routing. Telegram enforces one webhook per bot token via API; calling setWebhook replaces prior URL. [core.telegram.org/bots/api#setwebhook]

**Result:** Webhooks required for multi-bot SaaS. Polling doesn't scale; webhooks do.

---

## 2. Multiplexing on ASGI (FastAPI)

**Single Endpoint Pattern:** 
- Set webhook for bot N to `https://yourdomain.com/webhook/{bot_token}` or `/webhook/{bot_id}` 
- FastAPI route: `POST /webhook/{bot_id}` receives raw Telegram Update JSON
- Lookup bot config (token, handlers) from DB by bot_id, route to processor

**PTB v21 + FastAPI:** [freecodecamp.org/news/how-to-build-and-deploy-python-telegram-bot-v20-webhooks/] Shows lifespan async context manager for setWebhook on app startup, single endpoint for update processing. PTB's `Application.process_update()` feeds Update directly into handlers without polling.

**Lighter Approach (No PTB Overhead):** Raw `Bot(token).get_updates()` or manual update dispatch avoids Application complexity. PTB Conversation/Persistence aren't necessary for forwarding bots.

**aiogram Pattern:** [docs.aiogram.dev/en/latest/dispatcher/webhook.html] Recommends separate endpoints per bot (not token-based routing) for security. Example: `/bot/{bot_id}/webhook` with `secret_token` validation per route.

**Recommendation:** FastAPI + per-bot endpoint + manual `Bot.send_message()` / `copy_message()` is simpler than PTB Application overhead.

---

## 3. Dynamic Add/Remove at Runtime

**Add bot:**
1. Validate token via `Bot(token).get_me()` - returns User or raises BadRequest
2. Insert bot config to DB (token, chat_pair mappings, user_id)
3. Call `setWebhook(url=https://yourdomain.com/webhook/{bot_id}, secret_token=random_string)`
4. Webhook active; ready to receive updates

**Remove bot:**
1. Call `deleteWebhook(drop_pending_updates=True)` - unsets webhook
2. Mark bot inactive in DB or delete record
3. No server restart needed; FastAPI route returns 404 if bot_id not in DB

**Feasibility:** Fully feasible. Webhook (de)activation is synchronous API call, <1s per bot. Can add/remove 100+ bots without restart.

**Issue:** Telegram's setWebhook is idempotent but replaceable; if user pastes same token twice, setWebhook re-registers same webhook (no harm).

---

## 4. Shared Forwarding Logic

**Per-Bot Route Config:** Store in DB:
```
table: bots
  id, user_id, token, active, secret_token

table: forward_rules  
  id, bot_id, source_chat_id, dest_chat_id
```

**Unified Handler:**
```python
async def forward_update(bot_id, update_dict):
  bot = Bot(token_from_db[bot_id])
  rules = db.get_forward_rules(bot_id)
  for rule in rules:
    if update_dict['message']['chat']['id'] == rule.source_chat_id:
      await bot.copy_message(rule.dest_chat_id, rule.source_chat_id, update_dict['message']['message_id'])
```

**Deployment:** Single FastAPI endpoint + route lookup + shared copy_message logic. Each bot has independent token/config; logic reused.

---

## 5. Rate Limits & Scaling

**Telegram Rate Limits:**
- 30 messages/second per bot globally
- 1 message/second to same chat
- Webhook IP must be stable; Telegram retries ~5min if endpoint unreachable

**Per-Bot Limits:** Track outgoing copy_message calls per bot. Use asyncio.Semaphore(30) for concurrent requests across all bots.

**VPS Capacity:** 
- 1 small VPS (1 CPU, 2GB RAM) handles ~50–100 bots with webhooks (per anecdotal reports)
- Polling: ~5–10 bots before CPU saturation
- Webhook: O(1) per bot; scales to network I/O limits

**Concurrency:** Handle webhook updates concurrently via `asyncio.gather()` or task queues. PTB's `handle_as_tasks=True` or FastAPI's native async handles 10K+ concurrent requests.

---

## 6. Token Validation

**getMe() Call:** [github.com/python-telegram-bot/python-telegram-bot/issues/33]
- `Bot(token).get_me()` returns User object if valid, raises BadRequest if revoked/invalid
- Caches result internally; cache stale after token changes (call again to refresh)
- ~200ms per call (one HTTP roundtrip to Telegram)

**Validation Flow:**
```python
async def validate_token(token: str) -> bool:
  try:
    bot = Bot(token)
    await bot.get_me()
    return True
  except BadRequest:
    return False
```

**On User Submit:** Call getMe() once to validate before saving to DB. If invalid, reject with "Token not recognized" error. Handles revoked/fake tokens upfront.

---

## 7. Webhook Security

**Secret Token:** [core.telegram.org/bots/api#setwebhook] Optional 1–256 char string (A-Z, a-z, 0–9, _, -). Telegram sends `X-Telegram-Bot-Api-Secret-Token` header on each update. Verify header matches setWebhook secret.

**FastAPI Middleware:**
```python
@app.post("/webhook/{bot_id}")
async def webhook(bot_id: str, request: Request):
  secret = db.get_bot_secret(bot_id)
  if request.headers.get("X-Telegram-Bot-Api-Secret-Token") != secret:
    return {"ok": False}  # Reject spoofed requests
```

**URL Secrecy:** Include bot_id in URL path; Telegram knows bot's token anyway (nobody else does). Secret token adds defense-in-depth against network sniffing.

---

## 8. Deployment Architecture

**Production Setup:**
- **Reverse Proxy:** nginx/Caddy on public domain + SSL (Telegram requires HTTPS)
- **FastAPI:** Behind proxy on localhost:8000
- **DB:** PostgreSQL/SQLite for bot configs, forward rules
- **Cloud Tunnel Option:** Cloudflare Tunnel for HTTPS without static IP (setWebhook supports tunnel URLs)

**Windows Dev:** Use ngrok/localtunnel to expose localhost:8000 as HTTPS URL, test locally with real Telegram.

---

## Summary

| Aspect | Finding |
|--------|---------|
| **Scaling** | Webhooks mandatory; polling unscalable beyond ~10 bots |
| **Multiplex** | FastAPI + per-bot route + manual Bot dispatch; PTB overhead optional |
| **Dynamic** | Add/remove at runtime via setWebhook/deleteWebhook; no restart |
| **Logic** | Shared copy_message logic across all bots; per-bot config in DB |
| **Limits** | ~50–100 bots per small VPS; rate-limit concurrent copy_message |
| **Validation** | getMe() call on token submit; caches result internally |
| **Security** | Use secret_token header validation + HTTPS mandatory |

---

## References

- [core.telegram.org/bots/api#setwebhook](https://core.telegram.org/bots/api#setwebhook)
- [freecodecamp.org - Python Telegram Bot v20 Webhooks](https://www.freecodecamp.org/news/how-to-build-and-deploy-python-telegram-bot-v20-webhooks/)
- [docs.aiogram.dev/en/latest/dispatcher/webhook.html](https://docs.aiogram.dev/en/latest/dispatcher/webhook.html)
- [python-telegram-bot getMe validation discussion](https://github.com/python-telegram-bot/python-telegram-bot/issues/33)
- [github.com/b0g3r/fastapi-security-telegram-webhook](https://github.com/b0g3r/fastapi-security-telegram-webhook)

---

## Unresolved Questions

- Exact rate-limit enforcement strategy (queue vs. backpressure) for 100+ bots
- Database schema for distributed multi-tenant scaling (sharding strategy)
- Handling Telegram webhook retries and idempotency (message deduplication)
