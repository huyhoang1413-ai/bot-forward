# Phase 04 — Services + UI (configure topic routes)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..03

## Overview
- Date: 2026-10-19
- Description: Let the admin create topic-scoped routes (optional source/dest topic ids), with bidirectional swapping both chat AND thread; show topic ids in the route list.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Topic ids are optional inputs → blank = whole group / General (backward compatible form).
- Bidirectional bridge must swap the thread ids too: (dstChat,dstThread) → (srcChat,srcThread).

## Requirements
- `add_route(session, bot_id, source, dest, bidirectional, source_thread_id=None,
  dest_thread_id=None)`; dedup includes thread ids; reverse route swaps chat+thread.
- `create_route` endpoint accepts optional `source_thread_id`, `dest_thread_id` form fields.
- bot_detail route list shows topic ids (e.g. `-100… ▸topic 12 → -100… ▸topic 5`).
- Users get the ids by running `/chatid` inside a topic (phase-02).

## Architecture
```python
# services.add_route
pairs = [(source, source_thread_id, dest, dest_thread_id)]
if bidirectional:
    pairs.append((dest, dest_thread_id, source, source_thread_id))  # swap chat+thread
for src, sthr, dst, dthr in pairs:
    exists = session.exec(select(Route).where(
        Route.bot_id==bot_id, Route.source_chat_id==src, Route.source_thread_id==sthr,
        Route.dest_chat_id==dst, Route.dest_thread_id==dthr)).first()
    if exists: continue
    session.add(Route(bot_id=bot_id, source_chat_id=src, source_thread_id=sthr,
                      dest_chat_id=dst, dest_thread_id=dthr))
```
```python
# ui.create_route  (parse blank -> None)
def _opt_int(v): 
    v=(v or "").strip(); return int(v) if v else None
services.add_route(session, bot_id, source_chat_id, dest_chat_id, bidirectional,
                   source_thread_id=_opt_int(source_thread_id),
                   dest_thread_id=_opt_int(dest_thread_id))
```
Template (bot_detail.html "Thêm tuyến forward"): two extra optional number inputs
"Topic nguồn (tuỳ chọn)" + "Topic đích (tuỳ chọn)" with a hint: *"Gõ /chatid trong topic để lấy
message_thread_id. Để trống = cả nhóm / General."* Route summary line appends
`{% if r.source_thread_id %} · topic {{ r.source_thread_id }}{% endif %}` → `{{ r.dest_thread_id }}`.

Note: the per-group sender UI groups by `source_chat_id`; topics don't change sender gating.
The route list still groups by source_chat_id; show per-route thread ids within the group block.

## Related code files
- `webapp/app/services.py` — `add_route` signature + dedup + bidirectional swap.
- `webapp/app/ui.py` — `create_route` optional thread fields.
- `webapp/app/templates/bot_detail.html` — route form inputs + route line topic display.

## Implementation Steps
1. Extend `add_route`.
2. Extend `create_route` form parsing.
3. Template: inputs + route line display.
4. Tests (services add_route topic + bidirectional swap; UI create_route).

## Todo list
- [ ] add_route topic args + bidirectional swap + dedup
- [ ] create_route optional thread fields
- [ ] bot_detail form + route line topic ids
- [ ] services + UI tests

## Success Criteria
- Creating a bidirectional topic route yields two rows with chat+thread swapped.
- Blank topic fields → NULL (whole group), identical to today.
- Route list shows topic ids when set.

## Risk Assessment
- Low-medium. Dedup must include thread ids (else a topic route collides with a whole-group one).

## Security Considerations
- Route endpoints already behind `require_auth` + `require_bot_access` (team isolation). Thread
  ids are plain ints; no new surface.

## Next steps
Phase 05: end-to-end tests + docs.
