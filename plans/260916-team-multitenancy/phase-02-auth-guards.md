# Phase 02 — Auth rework + guards

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (User model + get_user_by_username)
- Research: [researcher-01-auth-rbac.md](./research/researcher-01-auth-rbac.md)

## Overview
- Date: 2026-09-17
- Description: Make login authenticate DB users OR the `.env` super-admin; store identity in session; replace the single `require_admin` with `require_auth` + `require_super_admin`; enforce team ownership inside `require_bot_access`.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- One central per-bot guard (`require_bot_access`, already on every `/bots/{id}` route) is the cleanest place to add team isolation → minimal churn, no route left unguarded.
- Starlette does NOT rotate session on login → clear+repopulate to prevent fixation.
- Constant-time + dummy-hash prevents username enumeration/timing.

## Requirements
- `login()`: DB-first (`get_user_by_username` + `verify_password`), fallback `.env` admin
  (`hmac.compare_digest`), dummy PBKDF2 when user missing, generic error, rotate session.
- Session keys: `user_id|None`, `username`, `is_admin`, `team_id|None`. Drop bare `authed`
  (derive `is_authed` from presence of `username`).
- `require_auth` (any logged-in), `require_super_admin` (is_admin & team_id None), and
  `require_bot_access` extended: super-admin bypass; else `bot.team_id == session team_id` else 403.
- Keep per-bot password unlock behavior inside `require_bot_access`.

## Architecture
```python
# auth.py
def current_user(request) -> dict | None:
    u = request.session
    return u if u.get("username") else None

def require_auth(request):
    if not current_user(request):
        raise HTTPException(303, headers={"Location": "/login"})

def require_super_admin(request):
    require_auth(request)
    if not request.session.get("is_admin"):
        raise HTTPException(status.HTTP_403_FORBIDDEN)

def require_bot_access(bot_id, request, session=Depends(get_session)):
    require_auth(request)
    bot = session.get(Bot, bot_id)
    if bot is not None and not request.session.get("is_admin"):
        if bot.team_id != request.session.get("team_id"):
            raise HTTPException(status.HTTP_403_FORBIDDEN)   # cross-team IDOR
    # then existing per-bot password unlock check (unchanged)
    if bot and bot.access_password_hash and not is_bot_unlocked(request, bot_id):
        raise HTTPException(303, headers={"Location": f"/bots/{bot_id}/unlock"})

@router.post("/login")
async def login(request, username=Form(...), password=Form(...), session=Depends(get_session)):
    ident = authenticate(session, username, password)   # DB-first + .env fallback + dummy hash
    if not ident:
        return RedirectResponse("/login?error=1", 303)
    request.session.clear()                              # rotate (anti-fixation)
    request.session.update(ident)                        # user_id, username, is_admin, team_id
    return RedirectResponse("/", 303)
```
`authenticate()` lives in auth.py (or services): returns the ident dict or None. Super-admin ident = `{user_id:None, username:env_user, is_admin:True, team_id:None}`.

## Related code files
- `webapp/app/auth.py` — authenticate(), login(), guards (rename + add + extend), current_user.
- `webapp/app/ui.py` — replace `require_admin` imports/usages with `require_auth`
  (dashboard, create_bot, routes, allowed, senders, group, password) — `require_bot_access`
  already present on `/bots/{id}` routes, now also does team check.
- `webapp/app/main.py` — no change (SessionMiddleware already set).

## Implementation Steps
1. Add User import + `authenticate()` + rewrite `login()` with rotation.
2. Rename `require_admin`→`require_auth`; add `require_super_admin`; extend `require_bot_access`.
3. Update every `Depends(require_admin)` → `Depends(require_auth)` across ui.py.
4. Tests: DB-user login OK/bad, `.env` admin login, session keys set, cross-team `/bots/{id}` → 403, super-admin bypass.

## Todo list
- [ ] authenticate() DB-first + .env fallback + dummy hash
- [ ] login() rotate session + set identity
- [ ] require_auth / require_super_admin / team check in require_bot_access
- [ ] rename guards across ui.py
- [ ] auth tests (incl. cross-team 403)

## Success Criteria
- `.env` admin and a DB user can both log in; wrong creds → generic error, no enumeration.
- A team user gets 403 on another team's `/bots/{id}` (GET and POST).
- Super-admin reaches any bot.

## Risk Assessment
- Medium: guard rename touches many routes — miss one = a route with no auth. Grep to confirm no `require_admin` remains and every `/bots` route depends on `require_auth`.
- `require_bot_access` now needs `require_auth` first (order matters) — ensure it calls it.

## Security Considerations
- Session fixation (rotate), timing/enumeration (dummy hash + generic error), 403 vs 303 semantics, cookie flags unchanged. Logout clears session.

## Next steps
Phase 03 scopes listings + bot creation by team and surfaces identity in the UI.
