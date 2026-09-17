# Scout Report 01 — Team multi-tenancy (per-team bot visibility)

Author: main agent (firsthand — knows this codebase). Scope: webapp/.

## Goal (locked by user)
- **Team model**: a Bot belongs to a Team; all members of that team see/manage it.
- **1 user → 1 team** (simple; not multi-team).
- **Admin creates accounts manually** (no self-registration).
- **wefun2026 = super-admin** (from .env): sees ALL bots, manages teams/users. Stays.
- Non-admin user: only sees bots of their team.

## Current state (single-admin, no tenancy)
- Auth = ONE admin from `.env` (`ADMIN_USERNAME`/`ADMIN_PASSWORD`), session cookie flag `authed=True`. No users/teams tables. `Bot` has NO owner column.

## Key files + what changes

### Auth (biggest change)
- `webapp/app/auth.py`
  - `login()` (L56-67): compares against `.env` admin only. → must ALSO authenticate DB users (username+password_hash), set session `user_id`, `team_id`, `is_admin`.
  - `require_admin(request)` (L22-29): only checks `authed`. → rename/extend: `require_auth` (any logged-in) + `require_super_admin` (only .env admin).
  - `require_bot_access(bot_id,...)` (L43-53): only checks per-bot password. → ADD team-ownership check (user's team must own the bot, unless super-admin) — this is the core tenant isolation gate for all `/bots/{id}...` routes.
  - session helpers `is_authed`, `unlock_bot`, `is_bot_unlocked`.
- `webapp/app/pw.py` — `hash_password`/`verify_password` (PBKDF2) already exist → reuse for user passwords.

### Data model
- `webapp/app/models.py`
  - Add `Team(id, name, created_at)`.
  - Add `User(id, username unique, password_hash, team_id FK, created_at)` (role optional; owner vs member later — YAGNI now).
  - `Bot` (L21-31): ADD `team_id: int | None` (FK team.id, index). Nullable for additive migration + super-admin/legacy bots.
- `webapp/app/db.py`
  - `create_all` makes new tables. Additive `ADD COLUMN team_id` handled by existing `_add_missing_columns()` (nullable → OK).
  - Optional seed: create a default team + assign existing bots to it (fresh DB on VPS → minimal).

### Query scoping (tenant isolation — every bot listing/mutation)
- `webapp/app/ui.py`
  - `dashboard` (L31-43): lists ALL bots → filter by session team unless super-admin.
  - `bot_detail`, `create_route`, `remove_route`, `remove_bot`, `create_allowed`, `remove_allowed`, `edit_allowed_label`, `group_*`, `senders_page`, `set_password` → all under `/bots/{id}` → covered if `require_bot_access` enforces team ownership (defense in depth: also filter in queries).
  - `create_bot` (L46-63): set `Bot.team_id` = creator's team (super-admin may need a team picker or assigns to own/default).
- `webapp/app/services.py` — `add_bot()` signature must accept/set `team_id`. Other services operate by `bot_id` already scoped by the route guard.
- `webapp/app/webhook.py` — **unaffected by tenancy**: it's unauthenticated, keyed by `bot_id` + secret header. Tenancy is an admin-UI concern only. (Confirm: no change needed.)

### New UI (super-admin only)
- Account management pages: list/create Teams, list/create Users (assign team, set password). New routes + templates. Guard with `require_super_admin`.
- `templates/base.html` — show current user/team + logout; maybe an "Admin" nav for super-admin.
- `dashboard.html` — unchanged layout, just scoped data.

### Tests (real DB, no mocks) — extend
- New: auth for DB users, tenant isolation (user A cannot GET/POST bot of team B → 303/403), super-admin sees all, account CRUD, bot creation sets team_id, IDOR on every `/bots/{id}` route cross-team.
- Update: existing auth/login tests, `add_bot` calls (new team_id arg), `create_bot` UI test.

## Conventions to respect
- Session cookie (SessionMiddleware, Secure in prod). PBKDF2 via pw.py. No mocks. Vietnamese UI, English code. Additive migrations only. IDOR guards everywhere (pattern already used: bot_id-scoped deletes).

## Open questions for design
- Super-admin identity: keep pure-.env (no User row) vs seed a User row? (.env keeps it simple; but then `team_id`/`user_id` in session is None for admin → handle.)
- When super-admin creates a bot, which team owns it? (picker / a system team / unowned-visible-to-all).
- Legacy/unowned bots (`team_id NULL`): visible to super-admin only? assign on migration?
- Password reset / change-own-password for users (defer?).
- Role within team (owner/member) — needed now or defer (YAGNI)?
