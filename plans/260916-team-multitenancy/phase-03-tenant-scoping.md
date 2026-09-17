# Phase 03 — Tenant scoping (dashboard, create-bot, UI identity)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02
- Research: [researcher-02-tenant-model.md](./research/researcher-02-tenant-model.md) §2-§4

## Overview
- Date: 2026-09-17
- Description: Dashboard shows only the viewer's team bots (admin: all); new bots get the creator's team (super-admin picks a team); base template shows who's logged in + admin nav.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- With `require_bot_access` already enforcing team ownership (phase-02), the remaining gaps are the LIST view (dashboard) and the CREATE path (assigning `team_id`).
- DRY: one `visible_bots()` helper for the list; `assert_bot_team()` optional (guard covers per-bot).

## Requirements
- `visible_bots(session, team_id, is_admin)` → all bots if admin else `where(team_id==...)`.
- Dashboard uses it; route-count query scoped to the visible set.
- `create_bot`: regular user → `team_id = session team_id`. Super-admin → team from a form
  `<select>` (list_teams) or blank = admin-only (NULL).
- `services.add_bot(...)` accepts `team_id`.
- base.html: show `username` + team name; super-admin sees an "Quản trị" nav link.

## Architecture
```python
# services.py
def visible_bots(session, team_id, is_admin):
    q = select(Bot) if is_admin else select(Bot).where(Bot.team_id == team_id)
    return session.exec(q).all()

# ui.py dashboard
sess = request.session
bots = services.visible_bots(session, sess.get("team_id"), sess.get("is_admin"))

# ui.py create_bot
team_id = request.session.get("team_id")
if request.session.get("is_admin"):
    team_id = form_team_id or None          # picker; blank => admin-only
bot = await services.add_bot(session, token, access_password, team_id=team_id)
```
`add_bot` sets `Bot.team_id=team_id`. Non-admin user with `team_id=None` (edge: user not
assigned a team) → block create with a clear error ("Tài khoản chưa thuộc team nào").

Template (dashboard.html): add-bot form shows a team `<select>` ONLY for super-admin
(`{% if is_admin %}`). base.html header: `{{ username }}{% if team_name %} · {{ team_name }}{% endif %}`
+ `{% if is_admin %}<a href="/admin">Quản trị</a>{% endif %}`. Pass `is_admin`, `username`,
`team_name` via context (or read from request.session in a context processor).

## Related code files
- `webapp/app/services.py` — `visible_bots`, `add_bot(team_id=...)`.
- `webapp/app/ui.py` — dashboard (scoped list + counts), create_bot (team assignment + picker), pass identity to templates.
- `webapp/app/templates/dashboard.html` — team picker (admin only), unchanged layout otherwise.
- `webapp/app/templates/base.html` — identity + admin nav.

## Implementation Steps
1. `visible_bots` + `add_bot(team_id=...)`.
2. Dashboard: scoped bots + counts; pass `is_admin/username/team_name`.
3. create_bot: assign team_id (+admin picker + no-team guard).
4. Templates: base identity/nav, dashboard picker.
5. Tests: user sees only own team; admin sees all; create sets team_id; no-team user blocked.

## Todo list
- [ ] visible_bots + add_bot team_id
- [ ] dashboard scoped list/counts + identity context
- [ ] create_bot team assignment + admin picker + no-team guard
- [ ] base/dashboard template updates
- [ ] scoping tests

## Success Criteria
- User A (team 1) dashboard shows only team-1 bots; User B (team 2) only team-2; admin all.
- A user creating a bot → it appears for their teammates, not other teams.
- Super-admin can assign a new bot to a chosen team via picker.

## Risk Assessment
- Medium. Ensure the dashboard route-count query is also scoped (don't count other teams' routes). Edge: user with no team.

## Security Considerations
- List scoping is defense-in-depth atop the per-bot guard. Team picker options limited to real teams; server still validates `team_id` belongs to a team.

## Next steps
Phase 04 gives super-admin the UI to create teams/users.
