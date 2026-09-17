# Scout Report 01 — Password min length 8 → 3

Author: main agent (firsthand). Every reference to the "≥8" rule:

## Enforcement (the actual gate)
- `webapp/app/ui.py:463` — `admin_create_user`: `if len(password) < 8:` → `< 3`
- `webapp/app/ui.py:481` — `admin_reset_password`: `if len(password) < 8:` → `< 3`
  (These two are the ONLY server-side checks. `services.create_user` does not enforce length.)

## User-facing text
- `webapp/app/templates/admin.html:10` — error: "Mật khẩu phải từ 8 ký tự trở lên." → "3 ký tự"
- `webapp/app/templates/admin.html:44` — placeholder "mật khẩu (≥8 ký tự)" → "≥3"
- `webapp/app/templates/admin.html:63` — placeholder "mật khẩu mới (≥8)" → "≥3"
- `webapp/README.md:59` — "mật khẩu ≥8 ký tự" → "≥3"

## Test to update (else it breaks)
- `webapp/tests/test_admin_ui.py:57` `test_create_user_short_password_rejected` uses password
  `"abc"` (3 chars) expecting rejection. With min=3, "abc" becomes VALID → change the sample to
  `"ab"` (2 chars) so it still exercises the reject path.
- Other tests use ≥8-char passwords → still valid, no change.

## Notes
- No DB/migration/auth-flow change. Login itself never had a min-length gate (only account
  creation / password reset). Pure constant + copy + one test.
- No researchers needed: nothing external to investigate.
