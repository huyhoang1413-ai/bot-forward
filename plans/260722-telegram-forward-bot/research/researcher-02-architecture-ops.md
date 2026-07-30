# Research 02 — Architecture & Operations

## 1. Routing config design
- Store routes as list of `{source_chat_id, dest_chat_ids[]}`. For **bidirectional bridge** (user choice): two directed edges A→B and B→A, or a `bridge: [A, B]` entry expanded to both directions at load.
- **YAML** chosen (readable, comments, lists). `.env` holds only the **secret** `BOT_TOKEN`; YAML holds routes. [https://core.telegram.org/bots/features]
- **Getting a group chat_id**: add bot to group, send any message; bot logs `update.effective_chat.id`. Supergroup IDs are large negatives (start `-100…`). Provide a `/chatid` command that replies with current chat id. [https://core.telegram.org/bots/api#chat]

## 2. Common forwarder features (scope per user: basic only)
- Topologies: one→many, many→one, **bidirectional bridge** (chosen). Bridge = loop risk: bot's own copied message must NOT be re-forwarded back (bot messages from itself; also guard by `message.from_user.is_bot` / bot id, and don't route a message that originated from the bot). 
- Deferred (YAGNI for v1): keyword filter, media-type filter, regex text replace, header/footer, link removal. Design route schema extensibly so filters can be added later without rewrite.

## 3. Edited / deleted messages
- **Edited**: Bot API delivers `edited_message` updates for chats bot is in. Syncing an edit requires knowing the destination message_id → needs a **message-id map** (persistence). Feasible but adds state.
- **Deleted**: Bot API does **NOT** send any update when a user deletes a message. Cannot detect deletions → cannot sync deletes. Hard limitation. [https://github.com/tdlib/telegram-bot-api/issues — known]
- Recommendation: v1 forwards NEW messages only (no edit/delete sync). Note as limitation. Edit-sync = optional later feature (requires SQLite map).

## 4. Persistence — minimal
- Basic bridge forwarding is **stateless** → **no database needed** for v1 (KISS/YAGNI). ✅
- DB (SQLite) only becomes necessary for: edit sync (id map), dedup, dynamic `/addroute`, stats. User chose file-config + basic forward → **skip DB**.
- Optional: in-memory dedup of `media_group_id` if album-buffering added later.

## 5. Deployment (Windows/VPS)
- Secret mgmt: `.env` + `python-dotenv`; **never commit** token → `.gitignore`. [https://pypi.org/project/python-dotenv/]
- Run: `python -m bot` with `run_polling()`. Long-polling needs only outbound HTTPS — works behind NAT/home PC.
- Keep-alive options: (a) **Windows** — Task Scheduler "at startup" or NSSM to run as a service; (b) **Linux VPS** — `systemd` unit with `Restart=always`; (c) **Docker** — `restart: unless-stopped` (portable, recommended for VPS). [https://docs.docker.com/]
- Reliability: PTB handles network retries internally; wrap startup in try/except + logging; use `logging` module to file + stdout with rotation (`RotatingFileHandler`). Handle 429 via `AIORateLimiter`.

## 6. Admin control & security
- User chose **file config** → no runtime admin commands needed for v1. Keep only utility `/chatid`, `/start`, `/status`.
- If admin commands added later: gate by owner user-id allowlist (`ADMIN_IDS` in .env), check `update.effective_user.id`.
- Security: token in .env only; bot admin rights in groups should be minimal (needs "read messages" = just membership/admin; to post in dest needs send-message right). Avoid giving bot delete/ban rights.

## 7. Project structure (small Python bot)
```
bot-forward/
├── bot/
│   ├── __init__.py
│   ├── __main__.py       # entrypoint: load cfg, build Application, run_polling
│   ├── config.py         # load .env + routes.yaml, validate, build routing map
│   ├── router.py         # RouteTable: source_id -> [dest_ids], loop guard
│   └── handlers.py       # message handler (copy to dests), /chatid /start /status
├── config/
│   └── routes.example.yaml
├── tests/
│   ├── test_config.py
│   └── test_router.py
├── .env.example
├── .gitignore
├── requirements.txt
└── README.md
```

## Unresolved questions
- Confirm `copy_message` (no attribution) vs `forward_message`.
- Loop-prevention for bidirectional bridge: rely on "ignore messages sent by our bot" — confirm acceptable (human messages bridged both ways, bot's copies not re-bridged).
- Album (media_group) grouping: defer to v2? (recommend yes).
- Deploy target: local Windows PC vs VPS vs Docker — affects keep-alive doc section.
