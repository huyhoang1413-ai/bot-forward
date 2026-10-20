# Phase 04 — UI (toggle + captured names management)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..03

## Overview
- Date: 2026-10-20
- Description: A per-bot "Tự động gắn tên người gửi" toggle, and a "Tên đã ghi nhận" page to view captured senders (user_id, @username, first_name), edit an override, or delete.
- Priority: Medium
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Reuse the senders-page pattern (server-side search + offset pagination) — captured rows can be many.
- All routes behind `require_auth` + `require_bot_access` (team isolation + per-bot lock already apply).

## Requirements
- `POST /bots/{id}/auto-nick` — set `bot.auto_nick` (checkbox on bot_detail).
- `GET /bots/{id}/names?q=&page=` — list captured profiles (search by first_name/username).
- `POST /bots/{id}/names/{profile_id}/label` — set/clear label_override (reuse is_valid_label).
- `POST /bots/{id}/names/{profile_id}/delete` — remove a captured row.
- bot_detail shows the toggle + a link "Tên đã ghi nhận (N) →".

## Architecture
```python
# services
def set_auto_nick(session, bot_id, value: bool): ...
def list_profiles(session, bot_id, q="", page=0, page_size=PAGE_SIZE): ...  # (items,total)
def set_profile_override(session, profile_id, bot_id, label): ...  # validate + scope
def delete_profile(session, profile_id, bot_id): ...

# ui
@router.post("/bots/{bot_id}/auto-nick", deps=[require_auth, require_bot_access])
async def set_auto_nick(bot_id, auto_nick: str = Form(""), session=...):
    services.set_auto_nick(session, bot_id, bool(auto_nick))
    return RedirectResponse(f"/bots/{bot_id}", 303)

@router.get("/bots/{bot_id}/names", response_class=HTMLResponse, deps=[...])
async def names_page(bot_id, request, q="", page:int=0, session=...): ...  # names.html
# + /names/{id}/label and /names/{id}/delete (bot-scoped IDOR)
```
Template: bot_detail card "Nickname tự động" with a checkbox form (checked = bot.auto_nick) + help
"Bot tự lấy first_name của người gửi (ghi 1 lần, sửa được)." + link to names.html.
`names.html` mirrors senders.html: search form, table (first_name, @username, user_id,
[override input + Lưu], [Xoá]), pagination.

bot_detail context: add `auto_nick = bot.auto_nick`, `profiles_count` (cheap count).

## Related code files
- `webapp/app/services.py` — set_auto_nick, list_profiles, set_profile_override, delete_profile.
- `webapp/app/ui.py` — auto-nick toggle + names page + label/delete endpoints.
- `webapp/app/templates/bot_detail.html` — toggle card + link.
- `webapp/app/templates/names.html` — new.

## Implementation Steps
1. services profile CRUD + set_auto_nick + list/search.
2. ui endpoints + names.html.
3. bot_detail toggle card + count/link + context.
4. Tests (UI: toggle persists, list/search, override, delete, IDOR cross-team 403).

## Todo list
- [ ] services (toggle + profile list/override/delete)
- [ ] ui endpoints + names.html
- [ ] bot_detail toggle + link
- [ ] UI tests

## Success Criteria
- Toggling auto_nick persists and changes forwarding (verified in phase-05 e2e).
- Names page lists captured senders, search works, override + delete work, cross-team → 403.

## Risk Assessment
- Low-medium (UI). Clamp pagination; validate override via is_valid_label.

## Security Considerations
- Bot-scoped IDOR on profile label/delete; team isolation via require_bot_access.

## Next steps
Phase 05: e2e tests + docs.
