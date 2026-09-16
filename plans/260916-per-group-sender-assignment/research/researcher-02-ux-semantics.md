# Per-Group Sender Assignment: UX + Semantics Research

**Date:** 2026-09-16  
**Status:** Recommendation-ready  

---

## 1. UX Recommendation: Per-Group Details Checkbox Form

### Selected Approach: Per-Group `<details>` with Checkbox List

**Why this one:**
- Scales cleanly for "handful of senders × 5–20 groups" (common admin scenario).
- Reuses existing `<details>` block layout (bot-detail.html already wraps routes this way).
- Each group checkbox list lives in a collapsible block → no single massive matrix.
- Full-page POST/redirect fits architecture; no JS required.
- Progressive enhancement: plain HTML checkboxes work as-is; could add optional JS to "select all" per-group later.

### Rejected Alternatives (Brief)
- **Checkbox matrix (senders × groups):** Awkward at scale; 10 senders × 15 groups = 150 cells. Hard to scan, no visual grouping.
- **Per-sender multi-select:** Awkward UX (one form per sender, repeated); doesn't match existing patterns.

### Proposed Form Structure
```html
<!-- In "Tuyến forward" card, under each <details> block for a group: -->
<details class="group">
  <summary><b>{{ source_group_id }}</b> → destinations</summary>
  
  <div style="margin-top:10px">
    <!-- Existing delete-route forms stay here -->
    
    <!-- NEW: Per-group sender assignment -->
    <form method="post" action="/bots/{{ bot.id }}/groups/{{ source_group_id }}/senders" style="margin-top:16px; padding-top:10px; border-top:1px solid #ddd">
      <fieldset>
        <legend style="font-size:13px; font-weight:bold">Giới hạn người gửi (nhóm này)</legend>
        <p class="muted" style="font-size:12px; margin-top:4px">Chọn người được phép forward. Để trống = tất cả.</p>
        
        {% if all_senders %}
          {% for sender in all_senders %}
          <label style="display:block; margin:6px 0">
            <input type="checkbox" name="sender_ids" value="{{ sender.id }}" {% if sender.id in group_sender_ids %}checked{% endif %}>
            <code>@{{ sender.username }}</code> {% if sender.label %}<span style="color:#666">— {{ sender.label }}</span>{% endif %}
          </label>
          {% endfor %}
        {% else %}
          <p class="muted">Chưa thêm người gửi nào (xem khung "Người gửi" phía trên).</p>
        {% endif %}
        
        <div style="margin-top:12px">
          <button type="submit">Lưu</button>
          {% if group_sender_ids %}
            <span class="muted" style="margin-left:12px; font-size:12px">{{ group_sender_ids|length }} người được phép</span>
          {% endif %}
        </div>
      </fieldset>
    </form>
  </div>
</details>
```

### Field Specs
- **POST endpoint:** `/bots/{id}/groups/{source_chat_id}/senders`
- **Form params:**
  - `sender_ids[]` (array of AllowedSender.id) — from checkboxes.
  - No value = empty list (interpreted as "allow everyone for this group").
- **Redirect:** Back to `/bots/{id}#group-{source_chat_id}` (same page, scroll anchor).
- **Response:** Flash message: "Đã lưu giới hạn người gửi cho nhóm {id}" or "Xoá hạn chế → forward mọi người".

---

## 2. Semantics & Forwarding Logic

### Forwarding Rule Decision Tree

```
IF global_senders list is EMPTY:
  forward EVERYONE from EVERY group
    (ignore group-level assignments; legacy behavior preserved)

ELSE (global list non-empty):
  FOR EACH source_group:
    IF group has NO assigned senders (empty list in DB):
      forward EVERYONE in that group
        (per-group opt-in: unset = default-allow)
    ELSE:
      forward ONLY assigned senders in that group
```

### Rationale
1. **Backward-compatible:** If someone (current user) has 2 global senders + routes to 5 groups:
   - On deploy, all new `GroupSenderAssignment` rows are empty.
   - Query sees empty list → ignores groups, applies global 2-sender filter to all (no change).
   - Admin can then opt-in to per-group restrictions one group at a time.

2. **Least-surprising default:** Empty group list = "use the global list or forward everyone."
   - Safer than "empty = nobody" (which would silently break forwarding).
   - Matches SaaS patterns (e.g., IAM: no group membership = use org-wide defaults).

3. **Unassigning a sender:**
   - Remove them from global list → applies everywhere, instant.
   - Remove them from a group → only that group stops getting them (others unaffected).

### Data Migration (One-Time)
On first deploy with per-group schema:
1. Load all routes and their source_chat_ids.
2. For each unique source_chat_id, create a `GroupSenderAssignment(bot_id, source_chat_id, sender_ids=[])`.
3. Empty list = uses global list (backward-compatible).
4. Zero-downtime; no webhook interruption.

---

## 3. Schema Sketch (Backward-Compatible)

```python
class GroupSenderAssignment(SQLModel, table=True):
    """Per-source-group override of which senders are allowed.
    Empty sender list = use global default (allow all global senders, or all if global is empty).
    """
    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id")
    source_chat_id: int  # e.g., -1001234567890
    # JSON list of sender IDs; NULL or [] = "use global"
    sender_ids: list[int] = Field(default_factory=list, sa_column=Column(JSON))
    
    __table_args__ = (UniqueConstraint("bot_id", "source_chat_id"),)
```

**No changes to AllowedSender** — remains global, single table.

---

## 4. Vietnamese UI Labels (Accessibility)

| English | Vietnamese | Context |
|---------|------------|---------|
| "Global allowed senders" | "Người gửi được forward + nhãn" | Current title (keep) |
| "Leave empty → forward everyone" | "Để trống → forward mọi người" | Current help (keep) |
| "Per-group sender assignment" | "Giới hạn người gửi (nhóm này)" | Legend for group checkboxes |
| "Select who is allowed. Empty = all." | "Chọn người được phép forward. Để trống = tất cả." | Help text under legend |
| "X users allowed" | "X người được phép" | Count label after save button |
| "Saved group restriction" | "Đã lưu giới hạn người gửi" | Success toast |
| "Override" (optional UI) | "Ghi đè" or "Cấu hình riêng" | Future per-group nickname override button |

**Accessibility notes:**
- Use `<fieldset>` + `<legend>` for checkbox groups (not just a div with role=group).
- `<legend>` is screen-reader friendly; prefer over aria-label.
- Label text ≤32 chars; use tooltips or help text for details.
- Existing label styling is plain text; keep checkboxes left-aligned for easy scanning.

---

## 5. Optional: Per-Group Nickname Override

### Recommendation: **Defer (YAGNI)**

**Why:**
- Rare use case: most admins reuse same nickname globally.
- Adds complexity: another JSON field, UI overhead, form state.
- Current requirement: only "enable/disable per group" (no override mentioned).

**Future-proof schema:**
```python
class GroupSenderAssignment(SQLModel, table=True):
    # ... existing fields ...
    # NULL = use global nickname; dict mapping sender_id → override nickname
    nickname_overrides: dict[int, str] | None = Field(
        default=None, sa_column=Column(JSON)
    )
```
Add form controls later (button "Cấu hình riêng nick name") if admins ask.

---

## 6. Implementation Checklist (High Level)

- [ ] Add `GroupSenderAssignment` model + migration.
- [ ] Data migration script: pre-populate empty assignments for all routes.
- [ ] FastAPI endpoint: `POST /bots/{id}/groups/{source_chat_id}/senders`.
- [ ] Update bot_detail.html: inject checkbox form into each `<details>` block.
- [ ] Forwarding logic: apply decision tree above when checking if sender is allowed.
- [ ] Tests: verify backward compatibility (empty → uses global), per-group override, unassign behavior.

---

## 7. Unresolved Questions

1. **UI polish:** Should checkbox groups auto-collapse after save (for UX flow), or stay open?
   - Likely: stay open (admin may tweak multiple groups in one session).
   
2. **Bulk actions:** Later, add "Apply senders to all groups" button on global sender card?
   - Defer; not in scope.
   
3. **Audit trail:** Log which senders are assigned to which group (for troubleshooting)?
   - Defer; depends on logging strategy.

---

## References

- [Cloud Four: Checkbox Group Validation](https://cloudfour.com/thinks/progressively-enhanced-form-validation-part-3-validating-a-checkbox-group/)
- [UX Patterns: Checkbox](https://uxpatterns.dev/patterns/forms/checkbox)
- [MDN: aria-multiselectable](https://developer.mozilla.org/en-US/docs/Web/Accessibility/ARIA/Attributes/aria-multiselectable)
- [Adrian Roselli: Under-Engineered Multi-Selects](https://adrianroselli.com/2022/05/under-engineered-multi-selects.html)

---

**Recommendation Status:** Ready for implementation planning.
