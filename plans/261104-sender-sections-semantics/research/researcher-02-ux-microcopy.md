# UX Microcopy: Sender Controls Semantic Separation (Telegram Bot Admin Panel)

**Research Date:** 2026-11-04  
**Focus:** Vietnamese microcopy + layout patterns to separate display naming (A/B) from access control (C)

---

## 1. "Empty = Allow All" Allowlist Pattern — Best Practices

### Core Semantic Problem
- **Industry consensus:** Empty allowlist = "unrestricted" (allow everyone), NOT "deny all"
- **Critical:** This contradicts user intuition → must communicate explicitly
- Sources: [GitHub security discussions](https://github.com/openclaw/openclaw/issues/147342), [Fail-open pattern](https://security.unboundcompute.com/fail-open-access-control/)

### How Reputable Apps Signal "Empty = Allow All"
1. **Progressive activation pattern** (Discord, Slack roles)
   - Default state: allowlist empty → fully permissive
   - First entry added → switches to deny-by-default
   - **Microcopy:** "Trống = cho phép tất cả" (visibly state it once, near empty state)

2. **Explicit state distinction** (AWS security groups, Cortex)
   - Never collapse "null/omitted" with "explicitly empty" in parser
   - UI must signal difference: `[ ]` (empty but active) vs. `[not set]` (dormant)
   - **Microcopy:** "Danh sách trống: không có hạn chế" (empty list: unrestricted)

3. **Strong contextual labeling** (IP allowlists, access control)
   - Pair each empty state with verb indicating outcome: "Cho phép…", "Chặn…", "Bỏ qua..."
   - Never label empty permission fields as just "list" — add capability verb

### Anti-Pattern to Avoid
- **DON'T:** Say "danh sách trống → forward mọi người" in labeling text that could apply to Control A (display naming) → users conflate it with permission

---

## 2. Visual/Textual Separation: Display Naming vs. Permission Gate

### Layered Permission Model (Principle)
Permissions should exist in distinct layers; allow/deny controls for *access* must not visually blur with *display/metadata* controls. [Source: metadata vs. access separation](https://medium.com/design-bootcamp/metadata-as-description-and-control-the-risks-of-re-using-metadata-as-controls-in-interfaces-c43713e024a9)

### Layout Strategy
- **Section headings** must signal intent, not just list name
- **Helper text** must clarify what choosing/omitting actually *enables/restricts*
- **Icons/colors** to reinforce: A/B = neutral (naming), C = security/sensitive (red/orange)

### Pattern: Information Architecture Separation
```
┌─────────────────────────────────────────┐
│ DISPLAY NAME SECTION (Neutral aesthetic)│
│ ├─ Control A: Danh sách biệt danh chung │
│ │  Helper: "Gán nickname cho người gửi" │
│ ├─ Control B: Sử dụng tên gốc            │
│ │  Helper: "Tự động dùng first_name"    │
└─────────────────────────────────────────┘

┌─────────────────────────────────────────┐
│ ACCESS CONTROL SECTION (Alert aesthetic)│
│ ├─ Control C: Cho phép người gửi        │
│ │  Helper: "Trống = tất cả gửi tới …"  │
│ │  "Thêm username = chỉ họ được phép"   │
└─────────────────────────────────────────┘
```

**Visual cues:**
- Section A/B: Gray/neutral card background, no warning icon
- Section C: Slightly highlighted card, lock icon, or orange left border
- Remove visual parity (don't use same card styling)

---

## 3. Vietnamese Microcopy: Control A, B, C Headings + Helper Text

### Control A: "Người gửi được forward (danh sách chung)"
- **Heading:** "Biệt danh người gửi" (Sender Nickname)
- **Subheading:** "(Tùy chọn — không ảnh hưởng đến quyền forward)"
- **Helper text:** "Gán nickname cho mỗi người gửi để dễ quản lý. Tên sẽ hiển thị trong chat."
- **Empty state:** "Chưa có biệt danh. Sẽ hiển thị tên gốc."
- **Why:** Emphasizes this is *labeling*, clarifies it's display-only, avoids permission language

### Control B: "Nickname tự động"
- **Heading:** "Sử dụng tên gốc (first_name)"
- **Helper text:** "Khi bật: tự động dùng first_name của người gửi làm nickname."
- **Toggle label:** "Áp dụng tự động" (Apply automatically)
- **Why:** Isolates from Control C; clearly a *display preference*, not access

### Control C: "Người gửi được phép"
- **Heading:** "Quyền forward — Người gửi được phép" (Permission — Allowed Senders)
- **Subheading:** "(Kiểm soát ai được forward tới route này)"
- **Helper text:**
  - "Danh sách trống: **tất cả người trong nhóm được forward**"
  - "Thêm username: **chỉ họ được forward** (ví dụ: @username1, @username2)"
- **Placeholder:** "@username (thêm rồi nhấn Enter)"
- **Empty state chip:** `[ ] Tất cả được phép` (stylized badge, not edit field)
- **Why:** Uses *permission language* ("được phép", "quyền"), explicitly states empty=unrestricted, uses badge to show current state

---

## 4. Anti-Patterns to Avoid

| Anti-Pattern | Why It Fails | Fix |
|---|---|---|
| Same card styling for A, B, C | Users see three "list controls" and assume same function | Use distinct visual sections + icons |
| "Danh sách chung" heading for A without "(display)" clarifier | "Danh sách" = permission-adjacent term in Vietnamese | Add "(Biệt danh)" or "(hiển thị)" to clarify intent |
| Control C empty state shows empty input field | Looks broken or "waiting for input" | Show explicit badge: `[ ] Tất cả được phép` |
| No mention of "trống" semantics in C | Users assume empty field = nothing forwarded | **Must** state "Trống = tất cả gửi" in helper or label |
| Listing all three controls in one section | Blurs permission boundary | Separate A/B into "DISPLAY" section, C into "ACCESS CONTROL" section |
| Helper text for A says "trống → forward mọi người" | Conflates naming with permission | Never say permission outcome in A's helper; only say "hiển thị..." |

---

## 5. Implementation Guidance

### Heading + Helper Structure
- **Heading (3–4 words):** Immediately signals control purpose
  - A: "Biệt danh người gửi" ✓
  - C: "Quyền forward — Người gửi được phép" ✓
- **Subheading (optional, 7–10 words):** Clarifies scope / category
  - A: "(Tùy chọn — không ảnh hưởng đến quyền forward)"
  - C: "(Kiểm soát ai được forward tới route này)"
- **Helper text (1–2 sentences max):** States behavior + empty-state rule
  - C: "Danh sách trống: **tất cả được forward**. Thêm username: **chỉ họ được phép**."

### Visual Hierarchy (Sketch/Design)
1. **Card A + B:** Light background, no icons, neutral colors
2. **Card C:** Subtle orange/red left border OR lock icon + slightly darker background
3. **Spacing:** 24px between A/B group and C group

### Validation / Copy Review
- Run copy by a Vietnamese-speaking PM or QA to confirm "trống/danh sách/được phép" terms don't bleed permission semantics into display section

---

## Unresolved Questions
1. Should Control A also show a "per-route nickname override" in route details, or just global? (Affects scope of "danh sách chung")
2. Does Control B's auto-nickname apply *only* to users with empty Control A entry, or as fallback to all?
3. Is there a UI for bulk-add to Control C (paste list of @usernames) or only manual entry?
