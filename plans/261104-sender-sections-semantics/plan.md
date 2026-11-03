# Plan — Align the 3 sender sections with the intended spec

## Goal
Make the bot-detail UI behave + read EXACTLY per your 3 rules, and remove the foot-gun that caused the "chỉ 1 người forward" incident:
1. **Danh sách chung** = nick name thủ công (KHÔNG phải cổng chặn forward).
2. **Nickname tự động** = `first_name`, phần **trước dấu cách đầu tiên**.
3. **Người gửi được phép** (từng tuyến) = trống → forward mọi người; thêm username → chỉ họ. *(đã đúng)*

## Current state (audit)
Section 3 already correct. Section 1 is correct behaviorally (a nickname row never blocks) but its wording frames it as a gate → confusing. Section 2 uses the whole `first_name`, not the first token. The historical migration `_backfill_group_sender_assignments` is the only thing that ever auto-created hidden gates. Full audit: [reports/01-conformance-audit.md](./reports/01-conformance-audit.md).

## Principles
YAGNI/KISS/DRY. No behavior change to section 3 (it's right). Additive only. Real tests (no mocks). Keep "empty allowlist / unassigned group = forward everyone" intact.

## Phases
| # | Phase | Status | Priority | Needs deploy |
|---|-------|--------|----------|--------------|
| 01 | [Auto-nick = first token before space](./phase-01-auto-nick-first-token.md) | Not started | High | Yes |
| 02 | [UI wording: separate NICKNAME from PERMISSION](./phase-02-ui-wording-separation.md) | Not started | High | Yes |
| 03 | [Neutralize hidden-gate foot-gun](./phase-03-neutralize-backfill-footgun.md) | Not started | Medium | Yes |
| 04 | [Tests + deploy both VPS](./phase-04-tests-deploy.md) | Not started | High | Yes |

## Decisions
- **D1 (section 2): RESOLVED → first-token** (`"Minh Anh"→"Minh"`). Implement `first_token(first_name)` on the auto path (Phase 01).
- **D2:** keep the per-route "Thêm" box also adding to the global nickname list (shared storage) — recommended default, not blocking. Revisit only if confusion persists.

## Out of scope
- Rewriting the AllowedSender/assignment storage model. Changing worker/datetime/gating-by-user_id (separate plan 261104-fix-sender-gating-identity).

## Key files
- `webapp/app/services.py` (resolve_label/capture first-token), `webapp/app/forwarding.py` (helper if needed), `webapp/app/templates/bot_detail.html` + `senders.html`/`names.html` (wording), `webapp/app/db.py` (backfill), `webapp/tests/`.

## Rollback
All changes additive / text-only + a pure helper. Revert = redeploy prior commit.
