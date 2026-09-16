# Phase 03 — Services + UI + Template

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02
- Research: [researcher-02-ux-semantics.md](./research/researcher-02-ux-semantics.md) §1,§4

## Overview
- Date: 2026-09-16
- Description: Let the admin assign global senders to each source group via a per-group checkbox form; add service ops (replace-all, cascade cleanup) and wire the endpoint + template.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Reuse the existing per-group `<details>` block in the "Tuyến forward" card; add a `<fieldset>` of checkboxes (one per global sender), checked = assigned.
- Replace-all semantics per group keeps the endpoint simple + idempotent.
- Cascade: deleting a sender or bot must drop its assignments; deleting a group's last route should clean that source's assignments (best-effort).

## Requirements
- `services.set_group_senders(session, bot_id, source_chat_id, sender_ids)` — replace-all, bot-scoped (ignore sender_ids not belonging to bot; only for a source that is a real route source of the bot).
- `delete_allowed_sender` also deletes its `SenderGroupAssignment` rows.
- `remove_bot` deletes all the bot's assignments.
- `delete_route`: if no routes remain for that source, delete assignments for that `source_chat_id` (of that bot's senders).
- New endpoint `POST /bots/{id}/groups/{source_chat_id}/senders`.
- `bot_detail` passes, per source group, the set of assigned sender ids.

## Architecture
Service (services.py):
```python
def set_group_senders(session, bot_id, source_chat_id, sender_ids: list[int]) -> None:
    """Replace the set of senders assigned to one source group (bot-scoped)."""
    # validate source belongs to bot
    valid_src = session.exec(select(Route.source_chat_id).where(
        Route.bot_id == bot_id, Route.source_chat_id == source_chat_id)).first()
    if valid_src is None:
        return
    own = {s.id for s in session.exec(
        select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()}
    wanted = {sid for sid in sender_ids if sid in own}   # drop foreign/stale ids (IDOR)
    current = {a.allowed_sender_id: a for a in session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.source_chat_id == source_chat_id,
            SenderGroupAssignment.allowed_sender_id.in_(own or [-1]))).all()}
    for sid in wanted - set(current):
        session.add(SenderGroupAssignment(allowed_sender_id=sid, source_chat_id=source_chat_id))
    for sid in set(current) - wanted:
        session.delete(current[sid])
    session.commit()
```
Cascade helpers reuse `select(SenderGroupAssignment).where(allowed_sender_id.in_(...))`.

UI (ui.py):
```python
@router.post("/bots/{bot_id}/groups/{source_chat_id}/senders",
             dependencies=[Depends(require_admin), Depends(require_bot_access)])
async def set_group_senders_ep(bot_id: int, source_chat_id: int,
        sender_ids: list[int] = Form(default=[]), session=Depends(get_session)):
    services.set_group_senders(session, bot_id, source_chat_id, sender_ids)
    return RedirectResponse(f"/bots/{bot_id}", status_code=303)
```
`bot_detail` context add: `assigned_by_group: dict[int, set[int]]` built from assignments of the bot's senders, plus pass `allowed_senders` (already present) for the checkbox list.

Template (bot_detail.html) — inside each group `<details>`, after route delete forms:
```html
<form method="post" action="/bots/{{ bot.id }}/groups/{{ g }}/senders" style="margin-top:14px;border-top:1px solid #334155;padding-top:10px">
  <fieldset style="border:0;padding:0;margin:0">
    <legend style="font-size:13px;font-weight:600">Giới hạn người gửi (nhóm này)</legend>
    <p class="muted" style="font-size:12px">Chọn người được phép forward. Để trống = forward mọi người nhóm này.</p>
    {% for a in allowed_senders %}
      <label style="display:block;margin:6px 0">
        <input type="checkbox" name="sender_ids" value="{{ a.id }}"
               {% if a.id in assigned_by_group.get(g, []) %}checked{% endif %}>
        @{{ a.username }}{% if a.label %} <span class="muted">— {{ a.label }}</span>{% endif %}
      </label>
    {% else %}
      <p class="muted">Chưa có người gửi nào (thêm ở card phía trên).</p>
    {% endfor %}
    <div style="margin-top:8px"><button type="submit">Lưu</button></div>
  </fieldset>
</form>
```

## Related code files
- `webapp/app/services.py` — `set_group_senders` + cascade in `delete_allowed_sender`, `remove_bot`, `delete_route`.
- `webapp/app/ui.py` — new endpoint + `bot_detail` context (`assigned_by_group`).
- `webapp/app/templates/bot_detail.html` — checkbox fieldset in each group block.

## Implementation Steps
1. services: `set_group_senders` + cascade deletes.
2. ui: endpoint + `bot_detail` context.
3. template: fieldset form.
4. Manual click-through on bot 1 (needs unlock password): check/uncheck, verify persisted.

## Todo list
- [ ] services.set_group_senders (bot-scoped, replace-all)
- [ ] cascade in delete_allowed_sender / remove_bot / delete_route
- [ ] ui endpoint + context
- [ ] template checkbox form

## Success Criteria
- Checking/unchecking senders for a group persists and reloads correctly.
- Deleting a sender removes its checkboxes everywhere + assignment rows gone.
- Posting foreign/stale `sender_ids` is ignored (no cross-bot write).
- Posting to a non-source `source_chat_id` is a no-op.

## Risk Assessment
- Medium UI surface. Replace-all avoids drift. `Form(default=[])` handles "all unchecked" (empty → clears group → open).
- Note: unchecking all = open group (see plan.md open question #1).

## Security Considerations
- IDOR: endpoint guarded by `require_admin` + `require_bot_access`; service filters `sender_ids` to the bot's own senders and validates the source belongs to the bot.
- No secrets touched. Replace-all is deterministic (no race-sensitive increments).

## Next steps
Phase 04 adds tests + docs and greens the suite.
