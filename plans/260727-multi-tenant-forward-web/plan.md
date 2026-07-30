# Plan: Web Panel to Manage Many Forwarding Bots

## Goal
A self-hosted **single-admin web panel** where the owner pastes a bot token and the bot instantly gains the message-forwarding feature. Manages **many bots** from one FastAPI service using **webhooks**. Reuses the existing `copy_message` forwarding logic; routes stored per-bot in a database.

## Decisions (confirmed with user)
- **Users**: single admin panel — 1 `ADMIN_PASSWORD`, session cookie. **No registration, no users table, no per-user isolation/RLS.** (All bots belong to the admin.)
- **Runtime**: **webhooks** — one FastAPI endpoint `/webhook/{bot_id}`, Telegram pushes updates; scales to ~50–100 bots on a small VPS.
- **Deploy**: **VPS + Docker Compose** — web + Caddy (auto-TLS via Let's Encrypt). SQLite file on a volume.
- **Frontend**: **minimal server-rendered** — Jinja2 + plain HTML forms (no SPA, no CDN).
- **Stack**: FastAPI + SQLModel + **SQLite** (single-admin, low write volume; swap to Postgres later via `DATABASE_URL`). Bot tokens **encrypted at rest** (Fernet, KEK in env).

## Scope
**In**: admin login; add bot (paste token → validate via `getMe` → encrypt+store → `setWebhook`); remove bot (`deleteWebhook`); webhook receiver + shared forwarding dispatcher (copy_message, loop guard, `/chatid` `/start`); per-bot routes CRUD (directed + "bidirectional" helper); dashboard UI; Docker Compose + Caddy TLS; tests; docs.
**Out (v2)**: public multi-user SaaS/registration, analytics dashboard, keyword/media filters, album grouping, edit/delete sync, KEK auto-rotation, message queue/Redis.

## Constraints & known limits (carried from single-bot)
- No delete/edit sync (Bot API limit). Albums copy as separate messages.
- Needs a public HTTPS domain for webhooks (Caddy handles TLS; ngrok/Cloudflare Tunnel for local dev).
- Bot must be admin in each group (privacy mode off).

## Relationship to existing code
Existing single-bot (`bot/`) stays runnable standalone. The panel is a **new `webapp/`**; it reuses the forwarding concept (`RouteTable`/`copy_message`) but runs bots via webhook dispatch (raw PTB `Bot`, no `Application` polling).

## Phases
| # | Phase | Status | Progress | File |
|---|-------|--------|----------|------|
| 01 | Web app skeleton, config, DB, crypto, admin auth | ✅ Done | 100% | [phase-01](phase-01-skeleton-auth-db.md) |
| 02 | Bot lifecycle (validate, add/remove, webhook set) | ✅ Done | 100% | [phase-02](phase-02-bot-lifecycle.md) |
| 03 | Webhook receiver + forwarding dispatcher | ✅ Done | 100% | [phase-03](phase-03-webhook-forwarding.md) |
| 04 | Web UI (dashboard, add bot, routes, chatid) | ✅ Done | 100% | [phase-04](phase-04-web-ui.md) |
| 05 | Deployment (Docker+Caddy), tests, docs | ✅ Done | 100% | [phase-05](phase-05-deploy-tests-docs.md) |

**Implementation status (2026-07-27):** Built in `webapp/`. DB = SQLite (per decision). 18 real tests pass. Code-reviewed; fixes applied (delete-route IDOR scope, PUBLIC_URL guard, SQLite WAL, cookie max_age). Pending: real end-to-end webhook test (needs public HTTPS domain/tunnel).

## Research
- [researcher-01 — multi-bot webhook runtime](research/researcher-01-multibot-runtime.md)
- [researcher-02 — SaaS architecture](research/researcher-02-saas-architecture.md)

## Tech stack
Python 3.11+, FastAPI, SQLModel, PostgreSQL, python-telegram-bot v21 (`Bot`), cryptography (Fernet), Jinja2, HTMX, Caddy, Docker Compose.

## Open questions
1. DB: PostgreSQL (planned) vs SQLite (lighter for single-admin) — Postgres chosen for concurrent webhook writes; confirm.
2. Domain name ready for the VPS? (required for webhook TLS).
3. Route rate-limiting: simple `asyncio.Semaphore` for MVP vs a queue — Semaphore chosen; confirm.
