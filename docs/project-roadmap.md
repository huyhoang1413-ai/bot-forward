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
