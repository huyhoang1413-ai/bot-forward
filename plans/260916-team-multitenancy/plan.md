# Plan: Team multi-tenancy (per-team bot visibility)

Date: 2026-09-17 · Status: Ready for review · Priority: High

## Goal
Turn the single-admin panel into multi-user. **Team model**: a Bot belongs to a Team; all
members of that team see/manage it. **1 user → 1 team**. **Admin creates accounts** (no
self-registration). **wefun2026 (.env) = super-admin**: sees ALL bots + manages teams/users.

## Locked design (from research 01 auth + 02 tenant)
- **Schema**: `Team(id, name unique)`, `User(id, username unique, password_hash, team_id FK)`,
  `Bot.team_id: int|None` (nullable → additive migration + admin-only/legacy). Roles deferred.
- **Auth**: login tries DB user (PBKDF2 `verify_password`) then `.env` super-admin; dummy-hash for
  constant time; **rotate session** (clear+set) on login; generic error. Session keys:
  `user_id` (None=admin), `username`, `is_admin`, `team_id` (None=admin).
- **Guards**: rename `require_admin`→`require_auth`; add `require_super_admin`; **fold team-ownership
  into `require_bot_access`** (super-admin bypass) so every `/bots/{id}` route is isolated in one place.
- **Scoping (DRY)**: helpers `visible_bots(session, team_id, is_admin)` + `assert_bot_team(bot, ...)`.
  Dashboard lists team's bots (admin: all). Create-bot sets `team_id`=creator's team; super-admin
  picks a team (or admin-only NULL).
- **Integrity**: delete Team → block if it has users/bots. Delete User → plain (bots are team-owned,
  no orphan). Delete Bot → existing cascade. **Webhook unchanged** (bot_id+secret; tenancy is UI-only).
  `telegram_bot_id` stays globally unique (one webhook per token).

## Phases (each independently testable)
1. **phase-01-models-migration.md** — Team/User models + `Bot.team_id` + additive migration + account
   services (create/list/delete team & user, get_user_by_username).
2. **phase-02-auth-guards.md** — login DB-first+`.env` fallback+rotate; `require_auth`/`require_super_admin`;
   team-ownership in `require_bot_access`; rename across routes.
3. **phase-03-tenant-scoping.md** — dashboard `visible_bots`; create_bot team assignment (+admin picker);
   base template shows user/team + admin nav.
4. **phase-04-admin-ui.md** — super-admin pages: Teams + Users (create/list/delete, reset password).
5. **phase-05-tests-docs.md** — full isolation/IDOR matrix (cross-team 403, admin sees all), README, roadmap.

## Key files
- `webapp/app/models.py`, `db.py`, `auth.py`, `pw.py`, `services.py`, `ui.py`,
  `templates/` (base, dashboard, new admin templates), `webapp/tests/`.

## Backward-compat / deploy notes
- Additive migration only; `.env` super-admin login unchanged. Fresh prod DB → no legacy bots.
- After deploy: super-admin creates Teams + Users; users log in and see only their team's bots.

## Open questions / decisions for reviewer
1. **Super-admin bot ownership**: team picker on add-bot (recommended — admin can provision for a team)
   vs admin-only `team_id=NULL`. Plan uses **picker + optional blank=admin-only**.
2. **Password min length** = 8 (confirm).
3. **Roles inside a team** (owner/member) — deferred (YAGNI). OK?
4. **Self change-password** + **login rate-limiting** — deferred to a later phase. OK?
