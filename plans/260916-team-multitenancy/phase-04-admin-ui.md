# Phase 04 — Admin UI (Teams + Users management)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (services), phase-02 (require_super_admin)
- Research: [researcher-01-auth-rbac.md](./research/researcher-01-auth-rbac.md) §4

## Overview
- Date: 2026-09-17
- Description: Super-admin-only pages to create/list/delete Teams and Users (assign team, set/reset password). No self-registration.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- All routes guarded by `require_super_admin` (403 for non-admin). Reuse phase-01 services — this phase is UI + endpoints only.
- One `/admin` page can host both Teams and Users sections (KISS) to avoid extra templates.

## Requirements
- `GET /admin` (super-admin): list teams + users; forms to add team, add user (username, password,
  team select), delete team (blocked if non-empty → flash error), delete user, reset password.
- Validation: username unique + valid, password ≥ 8 chars, team exists.
- Errors surfaced via `?error=...` banners (existing pattern).

## Architecture
```python
# ui.py
@router.get("/admin", response_class=HTMLResponse, dependencies=[Depends(require_super_admin)])
async def admin_page(request, session=Depends(get_session)):
    return templates.TemplateResponse(request, "admin.html", {
        "teams": services.list_teams(session),
        "users": services.list_users(session),     # each with team name
        "error": request.query_params.get("error"),
    })

@router.post("/admin/teams", dependencies=[Depends(require_super_admin)])
async def admin_create_team(name=Form(...), session=Depends(get_session)):
    ok = services.create_team(session, name)
    return RedirectResponse("/admin" + ("" if ok else "?error=team"), 303)

@router.post("/admin/teams/{team_id}/delete", dependencies=[Depends(require_super_admin)])
async def admin_delete_team(team_id: int, session=Depends(get_session)):
    ok = services.delete_team(session, team_id)      # False if non-empty
    return RedirectResponse("/admin" + ("" if ok else "?error=team_not_empty"), 303)

@router.post("/admin/users", dependencies=[Depends(require_super_admin)])
async def admin_create_user(username=Form(...), password=Form(...),
                            team_id: int = Form(...), session=Depends(get_session)):
    if len(password) < 8: return RedirectResponse("/admin?error=pw_short", 303)
    ok = services.create_user(session, username, password, team_id)
    return RedirectResponse("/admin" + ("" if ok else "?error=user"), 303)

@router.post("/admin/users/{user_id}/delete", ...)          # delete_user
@router.post("/admin/users/{user_id}/password", ...)        # reset_user_password (len>=8)
```
Template `admin.html` (new, extends base): Teams card (list + add form + delete buttons),
Users card (table: username, team, [reset pw form], [delete]); add-user form with a team `<select>`.
Vietnamese labels. Show error banners for `team_not_empty`, `pw_short`, `user`, `team`.

## Related code files
- `webapp/app/ui.py` — /admin routes (all `require_super_admin`).
- `webapp/app/templates/admin.html` — new.
- `webapp/app/templates/base.html` — the "Quản trị" nav link already added in phase-03.

## Implementation Steps
1. Add /admin GET + team/user POST endpoints (super-admin guarded).
2. Create admin.html (teams + users sections + forms + error banners).
3. Manual check: create team, create user in it, log in as that user, delete blocked when non-empty.
4. Tests.

## Todo list
- [ ] /admin page + endpoints (teams/users create/delete, reset pw)
- [ ] admin.html template
- [ ] tests: super-admin only (403 for user), create/delete flows, non-empty team blocked

## Success Criteria
- Non-admin GET /admin → 403. Super-admin can create a team + user; the user can then log in.
- Deleting a team that still has users/bots is refused with a clear message.
- Password reset works; new password logs in, old fails.

## Security Considerations
- Every /admin route `require_super_admin`. Passwords hashed. Username normalized+unique.
- No secrets in redirects. Password never echoed back in HTML.

## Next steps
Phase 05: full isolation/IDOR test matrix + docs.
