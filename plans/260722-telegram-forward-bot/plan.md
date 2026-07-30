# Plan: Telegram Forward Bot (Bidirectional Bridge)

## Goal
Build a Python Telegram bot (Bot API) that bridges messages **bidirectionally between groups**, forwarding all message types (text, media, files, stickers…) cleanly. Routes configured via file (`.env` + `routes.yaml`). KISS/YAGNI — no database, no filters in v1.

## Decisions (confirmed with user)
- **Mechanism**: Bot API — bot must be **admin** in every bridged group (privacy mode off).
- **Topology**: bidirectional bridge (A↔B), extensible to more pairs via config.
- **Features**: basic forward of all message types only. No keyword/media filters (deferred).
- **Config**: `.env` (secret `BOT_TOKEN`) + `routes.yaml` (bridge pairs). Edit file → restart.
- **Library**: `python-telegram-bot` v21+ (async, `AIORateLimiter`, long polling).
- **Copy vs forward**: use `copy_message` (clean, no "Forwarded from"); one-line switch to `forward_message` if attribution wanted.

## Scope
**In**: scaffold, config loader, routing table + loop guard, message copy handler, utility commands (`/start`, `/chatid`, `/status`), logging, tests (config+router, no mocks), deploy docs (Windows/VPS/Docker), README.
**Out (v2)**: edit/delete sync, media-group/album grouping, keyword/regex filters, header/footer, dynamic `/addroute`, SQLite, webhooks.

## Constraints & known limits
- Deleted messages CANNOT be detected via Bot API → no delete sync.
- Album (media_group) messages copy as separate messages in v1 (documented limitation).
- Rate limits ~30 msg/s global, ~1 msg/s per chat → handled by `AIORateLimiter`.

## Phases
| # | Phase | Status | Progress | File |
|---|-------|--------|----------|------|
| 01 | Project scaffold & configuration | Not started | 0% | [phase-01](phase-01-scaffold-and-config.md) |
| 02 | Core forwarding engine & commands | Not started | 0% | [phase-02](phase-02-forwarding-engine.md) |
| 03 | Testing, deployment & docs | Not started | 0% | [phase-03](phase-03-testing-deployment-docs.md) |

## Research
- [researcher-01 — libraries & API](research/researcher-01-libraries-api.md)
- [researcher-02 — architecture & ops](research/researcher-02-architecture-ops.md)

## Tech stack
Python 3.11+, python-telegram-bot v21+, PyYAML, python-dotenv, pytest.

## Open questions (confirm before/at implementation)
1. Confirm `copy_message` (recommended) vs `forward_message`.
2. Deploy target: local Windows PC, Linux VPS, or Docker? (affects keep-alive setup — all documented).
3. Number of groups now: just 2 (single bridge) or several pairs? (config supports N pairs regardless).
