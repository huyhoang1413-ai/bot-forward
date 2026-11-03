# Phase 02 — UI wording: separate NICKNAME (A/B) from PERMISSION (C)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: none · Research: [research/researcher-02-ux-microcopy.md](./research/researcher-02-ux-microcopy.md)

## Overview
- Date: 2026-11-04
- Description: Rewrite the help text so the gate lives ONLY in section 3 ("Người gửi được phép"), and sections 1–2 read as purely about the display nickname. Stops users from thinking the global list restricts forwarding (the confusion behind the incident). Text-only change.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Anti-pattern present today: section 1 says "Danh sách trống → forward mọi người" — that is a GATE statement under the NICKNAME card → implies the list gates (researcher-02). Remove it.
- Keep section 3's current line (it's correct + clear): "Để trống = forward mọi người. Thêm username để chỉ forward những người đó."
- Per-group summary badge already shows "mọi người" / "N người được phép" ([bot_detail.html:68](../../webapp/app/templates/bot_detail.html#L68)) — keep; it's the right place for permission state.

## Requirements
- Section 1 heading/help → nickname registry, explicitly "không ảnh hưởng ai được forward".
- Section 2 help → auto nickname from first_name (first token, per Phase 01), display-only.
- Section 3 → unchanged wording (the single source of truth for permission).

## Architecture (copy — adjust freely)
`bot_detail.html` section 1 ([lines 35-44](../../webapp/app/templates/bot_detail.html#L35-L44)):
```
H3: Biệt danh người gửi (tuỳ chọn)
help: Đặt nick name hiển thị cho người gửi. CHỈ là tên hiển thị — KHÔNG quyết định ai được forward
      (việc đó cấu hình ở mỗi tuyến, mục "Người gửi được phép").
```
Section 2 ([lines 46-54](../../webapp/app/templates/bot_detail.html#L46-L54)):
```
help: Bật để bot tự lấy TÊN (first_name, phần trước dấu cách đầu tiên) của người gửi làm nick,
      gắn dạng [Tên] nội dung. Ghi nhận một lần (sửa/ghi đè được). Nhãn thủ công vẫn ưu tiên. Chỉ là tên hiển thị.
```
Section 3 ([lines 88-90](../../webapp/app/templates/bot_detail.html#L88-L90)): keep as-is (optionally add a badge "Tất cả được phép" when the group is open).
- Mirror the section-1 reframing in `senders.html` / `names.html` headers if they repeat the gate language.

## Related code files
- `webapp/app/templates/bot_detail.html` (sections 1,2,3), `webapp/app/templates/senders.html`, `webapp/app/templates/names.html`.

## Implementation Steps
1. Edit section 1 + 2 copy. 2. Remove the "Danh sách trống → forward mọi người" line from section 1. 3. Optional open-badge in section 3. 4. Scan senders/names templates for gate-sounding text; align.

## Todo list
- [ ] section 1 = nickname-only wording (no gate language)
- [ ] section 2 = mentions "trước dấu cách đầu tiên" + display-only
- [ ] section 3 wording unchanged / clarified
- [ ] senders.html / names.html aligned

## Success Criteria
- A new admin reads the page and correctly concludes: permission = section 3 only; sections 1–2 = display name.

## Risk Assessment
- Minimal (text). No logic change.

## Security Considerations
- None (copy only).

## Next steps
Phase 03: remove the hidden-gate foot-gun so wording matches reality for future bots too.
