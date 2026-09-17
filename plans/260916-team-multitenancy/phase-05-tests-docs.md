# Phase 05 — Isolation test matrix + docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..04
- Project rule: real DB, NO mocks.

## Overview
- Date: 2026-09-17
- Description: Consolidated cross-team isolation / IDOR tests across every `/bots/{id}` route, account-management auth, and login; update README + roadmap.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Isolation is only as strong as its weakest route → test EVERY `/bots/{id}` mutation cross-team, not just the dashboard.
- Existing 106 tests are the regression anchor; several login/UI tests change (session keys, add_bot team_id).

## Requirements
- Full suite green. Cross-team access blocked everywhere; super-admin unrestricted.

## Architecture / Test matrix
`test_auth.py` (extend/update):
- `.env` admin login → session `is_admin=True`, `team_id=None`.
- DB user login (created via service) → `is_admin=False`, correct `team_id`.
- wrong password / unknown user → redirect `?error=1` (generic), no enumeration.
- logout clears session.

`test_tenant_isolation.py` (new, TestClient, real DB): build 2 teams + a user each + a bot per team.
- Dashboard: user A sees only team-A bot; user B only team-B; admin sees both.
- For EACH route, user B on team-A's bot → 403; user A → OK; admin → OK:
  `GET /bots/{id}`, `POST /routes`, `/routes/{rid}/delete`, `/allowed`, `/allowed/{aid}/delete`,
  `/allowed/{aid}/label`, `/groups/{src}/senders(-inline)` add/remove, `/password`, `/delete`,
  `GET /bots/{id}/senders`, `GET /bots/{id}/groups/{src}/senders`.
- create_bot as user → bot.team_id == user's team; as admin with picker → chosen team.
- user with `team_id=None` → create_bot blocked.

`test_admin_ui.py` (new): non-admin GET/POST /admin* → 403; admin creates team+user; delete team
non-empty → refused; reset password works.

`test_services.py` (extend): team/user CRUD, delete_team blocked when non-empty, get_user_by_username.

Update: existing `add_bot` test calls (new `team_id` param); any login test asserting old `authed` key.

## Related code files
- `webapp/tests/test_auth.py`, `test_services.py` (update)
- new: `webapp/tests/test_tenant_isolation.py`, `test_admin_ui.py`
- `webapp/README.md`, `docs/project-roadmap.md`

## Implementation Steps
1. Update auth/services tests for new session + team_id.
2. Add isolation matrix test (loop over routes).
3. Add admin-UI auth tests.
4. README (multi-user/team section: how admin creates teams/users, what users see) + roadmap bullet.
5. `pytest -q` green.

## Todo list
- [ ] auth tests (env admin + db user + logout + generic error)
- [ ] tenant isolation matrix (every /bots/{id} route cross-team 403)
- [ ] admin-ui auth tests
- [ ] services team/user tests
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green.
- A single test proves user B cannot touch team-A's bot on ANY route (403), while admin can.
- Login/session behavior verified for both identity types.

## Risk Assessment
- Low (tests/docs). Main risk = missing a route in the matrix → keep the route list in sync with ui.py.

## Security Considerations
- The isolation matrix IS the security acceptance test. Also assert `/admin` is super-admin-only and webhook is unaffected by tenancy.

## Next steps
Deploy: `git pull && docker compose up -d --build`; super-admin creates teams/users.
