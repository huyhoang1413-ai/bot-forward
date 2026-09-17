# Phase 01 — Lower password minimum 8 → 3

## Context links
- Parent: [plan.md](./plan.md) · Scout: [scout-01-report.md](./scout/scout-01-report.md)
- Depends on: team-multitenancy feature (introduced the /admin account UI).

## Overview
- Date: 2026-09-17
- Description: Change the account-password minimum from 8 to 3 characters + sync UI/README copy + fix one test.
- Priority: Low
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Only two server-side gates enforce length (`admin_create_user`, `admin_reset_password`); everything else is display copy.
- One existing test asserts a 3-char password is rejected → must change its sample to 2 chars.

## Requirements
- Passwords with length ≥ 3 accepted; length < 3 still rejected with the `pw_short` error.
- UI + README say "3" not "8". Full suite green.

## Architecture
Single constant change in two handlers:
```python
# ui.py (both admin_create_user and admin_reset_password)
if len(password) < 3:
    return RedirectResponse("/admin?error=pw_short", status_code=status.HTTP_303_SEE_OTHER)
```
Copy: admin.html error → "Mật khẩu phải từ 3 ký tự trở lên."; placeholders "≥3". README "≥3".
(Optional/again YAGNI: could extract a `MIN_PW_LEN=3` constant — 2 uses, keep inline for KISS.)

## Related code files
- `webapp/app/ui.py` (L463, L481)
- `webapp/app/templates/admin.html` (L10, L44, L63)
- `webapp/README.md` (L59)
- `webapp/tests/test_admin_ui.py` (L64: `"abc"` → `"ab"`)

## Implementation Steps
1. Edit ui.py: `< 8` → `< 3` (both spots).
2. Edit admin.html: error text + 2 placeholders → "3".
3. Edit README: "≥8"→"≥3".
4. Edit test_admin_ui: short-pw sample → `"ab"`.
5. `pytest -q` → green.

## Todo list
- [ ] ui.py two constants → 3
- [ ] admin.html copy → 3
- [ ] README copy → 3
- [ ] test sample → "ab"
- [ ] pytest green

## Success Criteria
- Creating a user with a 3-char password succeeds; a 2-char password shows "pw_short".
- All tests pass.

## Risk Assessment
- Minimal. Weaker passwords are the only "risk" (accepted per user request).

## Security Considerations
- Lowering the floor reduces brute-force resistance. Acceptable for a small internal panel behind
  session auth; note there is no login rate-limiting yet (already tracked as deferred).

## Next steps
Commit + (optional) deploy: `git pull && docker compose up -d --build` on the VPS.
