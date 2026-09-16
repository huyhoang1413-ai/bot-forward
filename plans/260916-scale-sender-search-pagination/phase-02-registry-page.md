# Phase 02 — Registry manager page (/bots/{id}/senders)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (service helpers)
- Research: [researcher-02-ux-large-lists.md](./research/researcher-02-ux-large-lists.md) §4,§6

## Overview
- Date: 2026-09-16
- Description: Move the global sender registry off the bot-detail page onto a dedicated, searchable, paginated page with add / edit-nickname / remove. Bot-detail keeps only a count + link.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Bot-detail must stop rendering the full sender table (breaks at 1000). A count + link is enough.
- Reuse existing mutation endpoints (`/allowed`, `/allowed/{id}/delete`, `/allowed/{id}/label`) — only the VIEW changes to search+paginate; redirect back to the manager page.

## Requirements
- `GET /bots/{id}/senders?q=&page=` renders search box + paginated list (username, nickname, edit-label, remove) + add form.
- Add/edit/delete redirect back to `/bots/{id}/senders` (preserve `q`/`page` where sensible).
- Bot-detail registry card → `{{ count }} người` + "Quản lý người gửi →" link (or "Thêm..." when empty).

## Architecture
Route (ui.py):
```python
@router.get("/bots/{bot_id}/senders", response_class=HTMLResponse,
            dependencies=[Depends(require_admin), Depends(require_bot_access)])
async def senders_page(bot_id, request, q: str = "", page: int = 0,
                       session=Depends(get_session)):
    bot = session.get(Bot, bot_id) or ...redirect
    items, total = services.list_senders(session, bot_id, q, page)
    return templates.TemplateResponse(request, "senders.html", {
        "bot": bot, "items": items, "total": total, "q": q, "page": page,
        "page_size": services.PAGE_SIZE,
        "total_pages": max(1, -(-total // services.PAGE_SIZE)),
        "error": request.query_params.get("error")})
```
Redirect existing `create_allowed` / `remove_allowed` / `edit_allowed_label` to
`/bots/{bot_id}/senders` (instead of `/bots/{bot_id}`).

Template `senders.html` (new, extends base): back-link, search form (GET), add form
(username + nickname), table of `items` with per-row label-edit form + remove form, pagination
(`← Trang trước` / `Trang sau →`, "Trang X/Y (Z người)"). Vietnamese microcopy per research §6.

Bot-detail change (bot_detail.html): replace the whole registry card body with:
```html
<h3>Người gửi được forward (danh sách chung)</h3>
{% if senders_count %}
  <p><b>{{ senders_count }} người</b> đã khai báo · để trống = forward mọi người.</p>
  <a href="/bots/{{ bot.id }}/senders">Quản lý người gửi →</a>
{% else %}
  <p class="muted">Không giới hạn — đang forward mọi người.</p>
  <a href="/bots/{{ bot.id }}/senders">Thêm người gửi →</a>
{% endif %}
```
`bot_detail` context: add `senders_count` (cheap `func.count`); DROP the full `allowed_senders`
list + `assigned_by_group` (moved to per-group page in phase-03).

## Related code files
- `webapp/app/ui.py` — new `senders_page`; redraw redirects of allowed mutations.
- `webapp/app/templates/senders.html` — new.
- `webapp/app/templates/bot_detail.html` — slim registry card.

## Implementation Steps
1. ui.py: add `senders_page`; update 3 redirects.
2. Create `senders.html`.
3. Slim bot_detail registry card; add `senders_count` to context.
4. Manual check on bot 1 (unlock): search, paginate, add, edit label, remove.

## Todo list
- [ ] senders_page route + context
- [ ] senders.html template (search/paginate/add/edit/remove)
- [ ] bot_detail registry card → count+link
- [ ] redirects of allowed mutations → /senders

## Success Criteria
- Page shows ≤50 rows/page with working search + pagination on a 1000-row seed.
- Add/edit-label/remove work and land back on the manager page.
- Bot-detail no longer renders any full sender table.

## Risk Assessment
- Low-medium (UI). Ensure `page` bounds are clamped (page<0 or beyond last → empty but no error).
- Preserve IDOR guards already on the mutation endpoints.

## Security Considerations
- All routes behind `require_admin` + `require_bot_access`. Search `q` is parameter-bound (no injection). Escape output via Jinja autoescape (default on).

## Next steps
Phase 03 mirrors this for per-group assignment.
