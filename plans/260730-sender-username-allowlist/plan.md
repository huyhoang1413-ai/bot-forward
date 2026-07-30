# Plan: Forward Only Allowed Senders (per-group username allowlist)

## Goal
Let the admin restrict forwarding so a bot only forwards messages from **specified usernames**, applied to **both sides** of a bridge. Filter is per **source group** (per "nhóm/tuyến"): each source group gets an optional username allowlist. Builds on the existing `webapp/`.

## Decisions (confirmed with user)
- **Scope**: per **source group** (per route/group, not per-bot). A bidirectional bridge A↔B → set the allowlist on group A and on group B ("cả 2 phía").
- **Empty list = forward everyone** (backward-compatible; filtering is opt-in per group).
- **Match by username only** (case-insensitive, strip `@`). No user-id matching (accepted trade-off).
- **Whitelist** semantics ("only these"), not blacklist.

## Key technical facts (from research)
- `message.from.username` is **optional** — missing for users without a public username, and for **anonymous admins / channel posts** (`sender_chat`, no `from`). → when a group's list is non-empty, a message with **no username is NOT forwarded**.
- Usernames are **case-insensitive** and **mutable** → normalize (lowercase, no `@`); if someone changes/removes their username they stop matching (documented limit of username-only).
- Filtering slots cleanly into the existing pure `decide_action` / `build_jobs`; empty list short-circuits to allow-all.

## Scope
**In**: `AllowedSender(bot_id, source_chat_id, username)` table; sender extraction in `decide_action`; pure `is_sender_allowed`; `build_jobs` gate; webhook loads per-group allowlist; UI to manage per-source-group usernames (+ "apply to reverse group" helper for bridges); tests; docs.
**Out (v2)**: user-id fallback matching, per-route (vs per-group) granularity, blocklist, bulk import, audit log, filtering anonymous/`sender_chat` by chat id.

## Relationship to existing code
Extends `webapp/`. Only the forwarding decision + webhook load + one UI section change. Durable outbox, rate limiting, routes — unchanged. Empty allowlist keeps current behavior exactly.

## Phases
| # | Phase | Status | Progress | File |
|---|-------|--------|----------|------|
| 01 | Backend: model + filter + webhook wiring | Not started | 0% | [phase-01](phase-01-backend-filter.md) |
| 02 | Admin UI + docs | Not started | 0% | [phase-02](phase-02-ui-docs.md) |

## Research
- [researcher-01 — Telegram sender fields](research/researcher-01-sender-fields.md)
- [researcher-02 — allowlist design](research/researcher-02-allowlist-design.md)

## Tech stack
Unchanged: FastAPI, SQLModel, SQLite, python-telegram-bot v21, Jinja2.

## Open questions
1. Anonymous admins / channel-as-sender: when a group's list is non-empty they get blocked (no username). Acceptable? (assumed yes — they're not "specified users").
2. "Apply to reverse group" helper for bridges — build it, or let admin add per group manually? (plan includes the helper; low cost).
3. Should `/chatid` `/start` stay ungated by the allowlist? (plan: yes — utility/setup commands always work).
