# Project Roadmap — BOT-Forward

Telegram message-forwarding, from a single bot to a multi-bot web panel.

## Status snapshot (2026-07-27)

| Milestone | Status | Location |
|-----------|--------|----------|
| M1 — Single-bot bidirectional forwarder | ✅ Done | `bot/` |
| M2 — Web panel managing many bots (webhook) | ✅ Done | `webapp/` |
| M2 — Real end-to-end forwarding verified | ✅ Done (2026-07-27, via Cloudflare tunnel) | copyMessage 200 OK both ways |

## M1 — Single bot (shipped)
- `bot/` — python-telegram-bot, long polling, `copy_message`, bidirectional bridge.
- Config: `.env` (token) + `config/routes.yaml`. Tests: 13 pass.
- Docs: [bot README](../README.md). Deploy: Windows (Task Scheduler/NSSM), systemd, Docker.

## M2 — Web panel (code complete)
- `webapp/` — FastAPI + SQLModel + **SQLite**; single-admin login.
- Many bots via **webhooks** (`/webhook/{bot_id}`); tokens **Fernet-encrypted** at rest.
- Paste token → `getMe` validate → `setWebhook` → configure routes in UI → forward live.
- **Reliability (2026-07-27):** durable outbox (`forward_job` table) + background worker — no message loss (retry until delivered), strict per-destination ordering, rate-limited (AIORateLimiter 30/s + 20/min per group), cached ExtBot (no getMe per update). Webhook now just enqueues + acks.
- **Sender allowlist (2026-07-30):** per-source-group username whitelist — only forward messages from designated usernames (both sides of a bridge via "apply to both sides"). Empty list = forward all (backward compatible). Match by username (case-insensitive); no-username/anonymous blocked when a list is set. Plan: [plans/260730-sender-username-allowlist/plan.md](../plans/260730-sender-username-allowlist/plan.md).
- **Sender labels, merged with allowlist (2026-07-30):** `label` is a column on `AllowedSender` — one per-source-group "senders" list where each username has an optional display name. Labeled messages get a `[Label]` prefix, preserving formatting via UTF-16 entity-offset shifting (text → send_message; caption media → copy_message caption override; caption-less → `[Label]` line then copy; over-limit → plain copy fallback, no loss). Labels apply only to allowlisted users. Plan: [plans/260730-per-username-display-labels/plan.md](../plans/260730-per-username-display-labels/plan.md).
- **Global senders + per-group assignment (2026-09-16):** the allowlist is a bot-wide registry of `username`+`label` (declared once); a `SenderGroupAssignment` junction table scopes each sender to specific source groups. Semantics: no senders → forward everyone; a source group with ≥1 assignment forwards only those, a group with none is open. Labels decouple from gating (a labeled sender is always prefixed). Additive migration backfills existing senders to all their groups (no behavior change).
- **Reply-aware forwarding (2026-11-01):** a forwarded reply is delivered as a reply to the dest copy of the original. New `MessageMap(bot_id, dest_chat_id, source_chat_id, source_message_id → dest_message_id)` captured after each send (copy_message→MessageId, send_message→Message). `ForwardJob` gains origin_chat_id/origin_message_id/reply_to_source_message_id/reply_quote; decide_action reads `reply_to_message`. The worker resolves the reply target at SEND time (per-dest id ordering ⇒ original mapped first), sets `ReplyParameters(allow_sending_without_reply=True)`, stores the map + deletes the job in one txn. No map ⇒ `↳ name: snippet` quote fallback (inline for text, leading line for media). 3-day prune in the worker. Works with topics + nickname. 158 tests.
- **Auto-nickname (2026-10-20):** per-bot `auto_nick` flag + `SenderProfile(bot_id, telegram_user_id, first_name, label_override, username)` (UNIQUE bot+user). Captures the sender's first_name ONCE from incoming messages (Bot API can't resolve a name by username) via `insert().on_conflict_do_nothing` + an in-process seen-cache; captures even when the flag is off (retroactive). Webhook resolves the per-message label (manual username-label > profile override > first_name when auto_nick) and passes a single sanitized `label` to build_jobs (replaced label_map). Applies to everyone incl. forward-everyone; anonymous/channel (no `from`) skipped. UI: toggle + "Tên đã ghi nhận" page (search/override/delete). 147 tests.
- **Topic-aware forwarding (2026-10-19):** forum (Topics) groups route per source/dest topic. `Route.source_thread_id`/`dest_thread_id` + `ForwardJob.dest_thread_id` (nullable, additive). Incoming topic = `message_thread_id` only when `is_topic_message` (avoids non-forum reply false positives); General/non-forum = None. A NULL-source route = whole group (all topics). Send passes `message_thread_id` to copy/send (None = General); topic errors are BadRequest/Forbidden → already permanent. Bidirectional bridge swaps chat+topic. `/chatid` in a topic reports + replies into that topic. Forum service messages skipped. 134 tests.
- **Team multi-tenancy (2026-09-17):** panel is now multi-user. `Team` + `User(team_id)` tables; `Bot.team_id` (nullable, additive). Login authenticates DB users OR the `.env` super-admin (DB-first, dummy-hash anti-enumeration, session rotate). Guards: `require_auth`/`require_super_admin` + team-ownership folded into `require_bot_access` (one gate for every `/bots/{id}` route). Members see only their team's bots; super-admin sees all + manages teams/users at `/admin` (admin-created accounts, no self-registration). Webhook unchanged (bot_id+secret). 122 tests incl. a cross-team IDOR matrix.
- **Scale sender UI to 500-1000 (2026-09-16):** replaced the render-all checkbox UI with dedicated manager pages — registry `/bots/{id}/senders` and per-group `/bots/{id}/groups/{source}/senders` — each with server-side prefix search (index `ix_allowedsender_bot_username` COLLATE NOCASE) + offset pagination (50/page) + incremental add/remove. Webhook allowlist fetch collapsed to a single LEFT JOIN (drops the 1000-id IN-list, sidesteps SQLite's param limit). Semantics unchanged.
- **Reliability (2026-07-30):** worker fails fast on permanent Telegram errors (e.g. "message can't be copied") so a bad message no longer blocks its destination queue. Additive SQLite auto-migration (ADD COLUMN) on startup.
- **Per-bot access password (2026-07-30):** optional password (PBKDF2-hashed) locks a bot's config page + mutations; session-remembered unlock; 🔒 on the dashboard. Does not affect webhook forwarding.
- **75 real tests pass** (worker ordering/retry/permanent-fail, unified sender allowlist+label, per-bot password gate, services, UI). Deploy: Docker Compose + Caddy (auto-TLS).
- Plan: [plans/260727-multi-tenant-forward-web/plan.md](../plans/260727-multi-tenant-forward-web/plan.md).
- **Remaining to go live:** point a domain at a VPS (or use ngrok/Cloudflare Tunnel for dev), set `PUBLIC_URL`, add a real bot, verify forwarding.

## Backlog (v2 — not started)
- Public multi-user SaaS (users table + registration + tenant isolation/RLS).
- Analytics/logs dashboard (message counts, errors).
- Message filters (keyword/media), header/footer, link stripping.
- Album (media_group) grouping; edit/delete sync.
- Rate-control via queue (Redis) for high bot counts; KEK rotation.

## Known limitations (both milestones)
- No delete/edit sync (Telegram Bot API limit).
- Albums copy as separate messages.
- Bot must be admin in each group (privacy mode off).
