# Report 01 — Conformance audit: 3 sections vs your spec

Date: 2026-11-04 · Bot detail UI. Compares each section's ACTUAL code behavior to the 3 rules you stated.

## Your spec (restated)
1. **"Người gửi được forward (danh sách chung)"** = đặt **nick name thủ công**.
2. **"Nickname tự động"** = lấy `first_name` = **phần trước dấu cách đầu tiên**.
3. **"Người gửi được phép"** (từng tuyến) = **trống → forward mọi người**; thêm username → chỉ những người đó.

## Verdict per section
| # | Section | Behaves as you say? | Gap |
|---|---------|---------------------|-----|
| 1 | danh sách chung | **Partly** | Rows are BOTH nickname AND the gate's membership pool. Help text says "gán họ cho từng nhóm" + "Danh sách trống → forward mọi người" = frames it as a GATE, not pure nickname. Confusing. |
| 2 | Nickname tự động | **No (behavior)** | Uses the WHOLE `first_name` field (can contain spaces, e.g. "Minh Anh"), not "text before first space". |
| 3 | Người gửi được phép | **Yes ✓** | Matches exactly: no assignment = open; add username = restricted. |

## Evidence
- Section 3 gate = per-source assignments — [forwarding.py:338-344](../../webapp/app/forwarding.py#L338-L344); empty/absent → open ([forwarding.py:256-258](../../webapp/app/forwarding.py#L256-L258)). **Correct.**
- Section 1 & 3 share the SAME `AllowedSender` rows: the per-route "Thêm" box calls `add_sender_by_username` → `add_allowed_sender` (creates global row) + `add_group_sender` (assignment) — [services.py:435-449](../../webapp/app/services.py#L435-L449). So they are one system surfaced twice → the confusion you hit.
- Section 1 alone does NOT gate: `add_allowed_sender` creates no assignment ([services.py:231-266](../../webapp/app/services.py#L231-L266)). GOOD — a nickname-only entry never blocks anyone. The ONLY thing that ever auto-created hidden gates was the one-time migration `_backfill_group_sender_assignments` ([db.py:124-157](../../webapp/app/db.py#L124-L157)) — the real cause of the "chỉ 1 người forward" incident.
- Section 2 auto-nick uses `first_name` verbatim: `sender_first_name = from_user.get("first_name")` ([forwarding.py:244](../../webapp/app/forwarding.py#L244)) → stored by `capture_sender` ([services.py:586-612](../../webapp/app/services.py#L586-L612)) → returned by `resolve_label` as `prof.first_name` ([services.py:639](../../webapp/app/services.py#L639)). No split-on-space.

## Research-confirmed facts
- `first_name` is required, CAN contain spaces/emoji/multi-word; `last_name` separate+optional. `split()[0]` (first whitespace token) is a sound "before first space" impl, with a fallback when the token is empty (pure whitespace/emoji) → use full name or user_id. (researcher-01)
- Allowlist UX: "empty = allow all" is standard but MUST be stated; a display-name concern and a permission concern on the same entities should be visually/textually separated; never put "trống → forward mọi người" under the NICKNAME section (implies it gates). (researcher-02)

## ⚠️ Key trade-off for section 2 (needs your call)
"Trước dấu cách đầu tiên" means "Minh Anh" → **"Minh"**, "Nguyễn Văn A" → **"Nguyễn"**. For Vietnamese given names that are 2 syllables this drops the 2nd syllable. Options:
- (a) First token only (exactly your words): "Minh Anh" → "Minh".
- (b) Keep full `first_name` (current): "Minh Anh" → "Minh Anh".
Decide in the plan review.

## Recommended fixes (minimal, KISS)
1. **Section 2**: truncate auto-nick to first token before space (per your spec) — single helper, applied at capture/resolve. (pending (a)/(b) decision)
2. **Section 1 wording**: reframe as pure nickname registry; remove the gate-sounding line; keep gating language ONLY in section 3.
3. **Foot-gun**: neutralize `_backfill_group_sender_assignments` so the nickname list never auto-creates gate assignments (prevents recurrence).
4. **Tests** asserting all 3 rules with real logic.

## Unresolved questions
- Section 2: option (a) first-token vs (b) full first_name? (Vietnamese 2-syllable names.)
- Do you want the per-route "Thêm" box to STOP also adding the person into the global nickname list (full decoupling), or is shared storage fine? (Recommend: keep shared — simpler, harmless.)
