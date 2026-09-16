# Phase 03 — Per-group manager page (/bots/{id}/groups/{source}/senders)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (helpers), phase-02 (pattern)
- Research: [researcher-02-ux-large-lists.md](./research/researcher-02-ux-large-lists.md) §1-§3

## Overview
- Date: 2026-09-16
- Description: Replace the per-group checkbox matrix with a dedicated page: a search picker (registry senders not yet assigned) + a paginated assigned list, each row added/removed one at a time. Bot-detail group blocks shrink to a count + link.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- The checkbox-per-sender form is the scale killer; incremental add/remove avoids ever posting the full list and never renders 1000 rows.
- Two lists: assigned (JOIN) and unassigned picker (anti-join), both search+paginated (phase-01 helpers).

## Requirements
- `GET /bots/{id}/groups/{source}/senders?q=&page=&aq=&apage=` renders picker (search `q`) + assigned list (search `aq`).
- `POST .../senders/{sender_id}/add` and `POST .../senders/{sender_id}/remove` (incremental, bot-scoped, redirect back preserving query).
- Bot-detail group block → `Quản lý N người cho nhóm này →` link (+ route delete forms stay). Remove the checkbox `<fieldset>` and retire `POST /bots/{id}/groups/{source}/senders` (replace-all) + `services.set_group_senders`.
- Validate `source` is a real route source (else redirect to bot detail).

## Architecture
Routes (ui.py):
```python
@router.get("/bots/{bot_id}/groups/{source_chat_id}/senders", response_class=HTMLResponse,
            dependencies=[Depends(require_admin), Depends(require_bot_access)])
async def group_senders_page(bot_id, source_chat_id, request, q="", page:int=0,
                             aq="", apage:int=0, session=Depends(get_session)):
    # verify source belongs to bot else redirect
    picker, ptotal = services.search_unassigned(session, bot_id, source_chat_id, q, page)
    assigned, atotal = services.list_group_senders(session, bot_id, source_chat_id, aq, apage)
    return templates.TemplateResponse(request, "group_senders.html", {...paging ctx...})

@router.post("/bots/{bot_id}/groups/{source_chat_id}/senders/{sender_id}/add",
             dependencies=[...])
async def group_add(bot_id, source_chat_id, sender_id, session=...):
    services.add_group_sender(session, bot_id, source_chat_id, sender_id)
    return RedirectResponse(f"/bots/{bot_id}/groups/{source_chat_id}/senders", 303)

@router.post(".../senders/{sender_id}/remove", ...)
async def group_remove(...):
    services.remove_group_sender(session, bot_id, source_chat_id, sender_id)
    return RedirectResponse(..., 303)
```
Template `group_senders.html` (new): two-column (picker | assigned), each with search form +
result rows (`Thêm` / `Xoá`) + pagination. Remove uses `onclick="return confirm('Xoá @...?')"`.
Desktop side-by-side, stacked on mobile (CSS `flex-wrap`). Microcopy per research §6.

Bot-detail group block (bot_detail.html): drop the checkbox `<fieldset>`; add:
```html
<p style="margin-top:12px">
  <a href="/bots/{{ bot.id }}/groups/{{ g }}/senders">
    Quản lý người gửi cho nhóm này{% if group_sender_counts.get(g) %} ({{ group_sender_counts[g] }}){% endif %} →
  </a>
</p>
```
`bot_detail` context: `group_sender_counts: dict[source -> count]` (one grouped count query),
replacing the removed `assigned_by_group`/`allowed_senders`.

Retire: delete `POST /bots/{id}/groups/{source}/senders` (replace-all) endpoint and
`services.set_group_senders` (+ its tests moved to incremental in phase-04).

## Related code files
- `webapp/app/ui.py` — group_senders_page + add/remove; remove old set_group_senders endpoint.
- `webapp/app/templates/group_senders.html` — new.
- `webapp/app/templates/bot_detail.html` — group block → count+link; remove fieldset.
- `webapp/app/services.py` — remove `set_group_senders` (superseded).

## Implementation Steps
1. ui.py: 3 routes (page + add + remove); delete old endpoint.
2. Create `group_senders.html`.
3. bot_detail: group block link + `group_sender_counts` context; remove fieldset.
4. services.py: delete `set_group_senders`.
5. Manual check on bot 1: search-add, remove, paginate.

## Todo list
- [ ] group_senders_page + add/remove routes
- [ ] group_senders.html (picker + assigned, paginated)
- [ ] bot_detail group block → count+link; remove fieldset
- [ ] retire set_group_senders (service + endpoint)

## Success Criteria
- With 1000 registry senders + a group of 300 assigned: page loads fast, picker excludes already-assigned, add/remove reflect immediately, pagination works on both lists.
- Bot-detail renders no per-sender checkboxes.

## Risk Assessment
- Medium (largest UI change). Ensure add/remove redirect keeps you on the group page (not bot detail) for flow.
- Retiring set_group_senders breaks `test_ui_group_senders` + `test_services` cases → updated in phase-04 (land together).

## Security Considerations
- IDOR: add/remove verified in services (sender.bot_id == bot_id, source is bot's route source). Routes behind `require_admin` + `require_bot_access`.
- Confirm-on-remove is UX only; server is authoritative.

## Next steps
Phase 04: tests + docs; green the suite.
