# Plan: Lower password minimum length 8 → 3

Date: 2026-09-17 · Status: Ready for review · Priority: Low

## Goal
Allow panel-account passwords from **3 characters** (was 8). Applies to admin-created users +
password reset. Trivial: change one constant in two places, sync UI copy, fix one test.

## Scope (from scout-01)
- `ui.py` ×2: `len(password) < 8` → `< 3` (admin_create_user, admin_reset_password).
- `admin.html` ×3: error text + 2 placeholders "8"→"3".
- `README.md` ×1: "≥8"→"≥3".
- `tests/test_admin_ui.py` ×1: short-password sample `"abc"` → `"ab"` (still <3 to test reject).

No researchers (nothing to research). No DB/auth-flow change. Login has no length gate.

## Phases
1. **phase-01-lower-min-length.md** — apply the constant + copy + test change, run `pytest`.

## Decision for reviewer
- Confirm **3** is the floor (weak passwords; acceptable for this small internal panel). If you
  later want per-length policy or "no minimum", say so — same code path.
