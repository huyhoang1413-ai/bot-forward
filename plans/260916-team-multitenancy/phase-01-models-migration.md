# Phase 01 — Models + Migration + Account services

## Context links
- Parent: [plan.md](./plan.md)
- Research: [researcher-02-tenant-model.md](./research/researcher-02-tenant-model.md)
- Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Depends on: none (foundation)

## Overview
- Date: 2026-09-17
- Description: Add `Team` + `User` tables and `Bot.team_id`; additive migration; service functions for team/user CRUD reused by the admin UI and auth.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `team_id` MUST be nullable → `_add_missing_columns()` can `ALTER TABLE bot ADD COLUMN` it without a table rebuild; NULL = admin-only/legacy.
- Bots are **team-owned, not user-owned** → deleting a user never orphans bots.
- Reuse `pw.py` PBKDF2 for user passwords (no new crypto).

## Requirements
- `Team(id, name unique, created_at)`; `User(id, username unique, password_hash, team_id FK, created_at)`.
- `Bot.team_id: int | None` FK team.id, indexed.
- Services: `create_team`, `list_teams`, `delete_team` (block if non-empty), `create_user`,
  `list_users`, `delete_user`, `reset_user_password`, `get_user_by_username`.
- Existing 106 tests still pass.

## Architecture
```python
# models.py
class Team(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_now)

class User(SQLModel, table=True):
    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)  # normalized lowercase
    password_hash: str
    team_id: int | None = Field(default=None, foreign_key="team.id", index=True)
    created_at: datetime = Field(default_factory=_now)

class Bot(SQLModel, table=True):
    # ...existing...
    team_id: int | None = Field(default=None, foreign_key="team.id", index=True)
```
Migration: `create_all()` makes team/user; `_add_missing_columns()` adds `bot.team_id`. No data backfill needed (fresh prod DB); NULL bots = admin-only.

Services (services.py) — reuse `hash_password`:
```python
def create_team(session, name) -> Team | None       # None if name blank/dup
def list_teams(session) -> list[Team]
def delete_team(session, team_id) -> bool            # False if team has users or bots
def create_user(session, username, password, team_id) -> User | None  # None if dup/invalid
def list_users(session) -> list[User]                # optionally join team name
def delete_user(session, user_id) -> None
def reset_user_password(session, user_id, password) -> None
def get_user_by_username(session, username) -> User | None
```
`delete_team` guard: `if users_in_team or bots_in_team: return False`.
Username normalized lowercase; password min length validated at UI layer (phase-04) + service.

## Related code files
- `webapp/app/models.py` — Team, User, Bot.team_id.
- `webapp/app/db.py` — (no new fn needed; `_add_missing_columns` handles team_id; new tables auto).
- `webapp/app/services.py` — account CRUD + `get_user_by_username`.

## Implementation Steps
1. Add Team, User models; add `team_id` to Bot.
2. Verify migration on a scratch DB (team_id column present, tables created).
3. Add account service functions.
4. Unit tests (services).

## Todo list
- [ ] Team + User models + Bot.team_id
- [ ] account services (team/user CRUD, get_user_by_username)
- [ ] tests: create/list/delete team (block non-empty), create/dup user, reset pw

## Success Criteria
- New tables + `bot.team_id` exist after startup (idempotent).
- `create_user` rejects duplicate username; `delete_team` refuses a non-empty team.
- `get_user_by_username` returns the row for `verify_password`.

## Risk Assessment
- Low. Additive schema. FK `ondelete` default RESTRICT at ORM level; enforcement of non-empty-team is done in service (SQLite FK enforcement is off unless PRAGMA), so rely on the service guard.

## Security Considerations
- Passwords hashed via PBKDF2 (`pw.hash_password`); never stored/logged plaintext.
- Username uniqueness enforced (unique constraint) → prevents impersonation.

## Next steps
Phase 02 wires these into login + guards.
