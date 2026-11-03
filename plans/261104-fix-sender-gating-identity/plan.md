# Plan — Fix sender gating: forward everyone, not just users with a @username

## Problem (one line)
@WeFunForward_bot forwards only "Antony" because the allowlist gate matches by **@username only**; members with no/changed username are silently dropped.

## Root cause
Gate = `is_sender_allowed(sender_username, allowed)` keyed on the mutable, optional Telegram `@username` ([forwarding.py:250](../../webapp/app/forwarding.py#L250)). A stable `telegram_user_id` is already captured per sender in `SenderProfile` but the gate ignores it. Full analysis: [reports/01-root-cause-analysis.md](./reports/01-root-cause-analysis.md).

## Goal
1. **Now**: restore forwarding for the affected routes (operational, no deploy).
2. **Durable**: gate by stable `telegram_user_id` (with username fallback) so anyone the admin intends to forward actually forwards — regardless of whether they have a public username.

## Principles
YAGNI/KISS/DRY. Additive migrations only (no destructive schema changes). No mock data in tests — test real logic. Keep the current "empty allowlist / unassigned group = forward everyone" semantics unchanged.

## Phases
| # | Phase | Status | Priority | Needs deploy |
|---|-------|--------|----------|--------------|
| 01 | [Diagnose + immediate unblock](./phase-01-diagnose-unblock.md) | Not started | **Critical** | No |
| 02 | [Schema: user_id on allowlist + backfill](./phase-02-schema-userid-backfill.md) | Not started | High | Yes |
| 03 | [Gate by user_id OR username (core fix)](./phase-03-gate-by-userid.md) | Not started | High | Yes |
| 04 | [UI: whitelist by captured profile](./phase-04-ui-add-by-profile.md) | Not started | Medium | Yes |
| 05 | [Tests + deploy both VPS](./phase-05-tests-deploy.md) | Not started | High | Yes |

## Decision gate (after Phase 01)
- If intent for the 2 routes = **forward everyone** → Phase 01 alone fixes it; Phases 02-05 become hardening (still recommended, lower urgency).
- If intent = **whitelist specific people** (some without usernames) → Phases 02-05 are the real fix. Do them.

## Out of scope
- Rewriting the allowlist storage model. Removing username support. Changing rate-limit/worker/datetime code (just fixed separately).

## Key files
- `webapp/app/forwarding.py` (gate), `webapp/app/webhook.py` (allowed-set build), `webapp/app/services.py` (capture/add), `webapp/app/models.py` (AllowedSender), `webapp/app/db.py` (migration/backfill), `webapp/app/ui.py` + templates (add-by-profile), `webapp/tests/`.

## Rollback
All code changes are additive + behind existing "unassigned group = open" semantics. Revert = redeploy previous commit; the new nullable column is harmless if unused.
