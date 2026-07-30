# Phase 01 — Backend: Allowlist Model + Filter + Webhook Wiring

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: existing `webapp/` (models, forwarding, webhook)
- Research: [researcher-01](research/researcher-01-sender-fields.md) (sender fields, normalization, edge cases), [researcher-02](research/researcher-02-allowlist-design.md) (schema, semantics)
- Docs: User object https://core.telegram.org/bots/api#user ; Message https://core.telegram.org/bots/api#message

## Overview
- **Date**: 2026-07-30
- **Description**: Add the `AllowedSender` table and enforce it in the pure forwarding decision. Webhook loads each bot's per-source-group allowlist and passes it to `build_jobs`. Empty list → unchanged behavior.
- **Priority**: High (core of the feature)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Filtering happens on the **sender of a message in a source group**, so key the allowlist by `(bot_id, source_chat_id)`. This covers fan-out (one source → many dests) with one list and matches "per nhóm".
- Keep it in the **pure** layer (`decide_action` extracts username; `is_sender_allowed` is a pure predicate) so it is testable with no DB/network/mocks.
- **Empty list = allow all** → `is_sender_allowed(sender, set())` returns True. Only a non-empty list restricts.
- Normalize usernames: `lstrip('@').lower()`. Missing username (None) + non-empty list → blocked.
- Commands (`/chatid`, `/start`) are decided before the forward branch → they stay ungated.
- Anonymous admins / channel posts have no `from.username` → blocked when list non-empty (documented limit).

## Requirements
- `models.AllowedSender`: `id, bot_id (index), source_chat_id (index), username (lowercased), created_at`; `UNIQUE(bot_id, source_chat_id, username)`.
- `forwarding.decide_action`: add `sender_username: str | None` to `Action` (normalized) for the "forward" case.
- `forwarding.is_sender_allowed(sender_username, allowed: set[str]) -> bool` (pure): `True` if `not allowed`, else `sender_username in allowed`.
- `forwarding.build_jobs(update, telegram_bot_id, routes, bot_id, allowed_map)`: new `allowed_map: dict[int, set[str]]` (source_chat_id → allowed usernames). For "forward", if `not is_sender_allowed(action.sender_username, allowed_map.get(source, set()))` → return `[]`.
- `webhook`: build `allowed_map` from `AllowedSender` rows for the bot; pass to `build_jobs`.
- `services`: helpers `add_allowed_sender(session, bot_id, source_chat_id, username, both_ways=False)` (normalize; dedup; optional add to reverse group), `delete_allowed_sender(session, id, bot_id)`; cascade-delete allowlist in `remove_bot`.

## Architecture
```
webapp/app/
├── models.py       # + AllowedSender
├── forwarding.py   # Action.sender_username, is_sender_allowed, build_jobs(allowed_map)
├── webhook.py      # load allowed_map -> build_jobs
└── services.py     # add/delete allowed sender, cascade on remove_bot
```
Decision flow (pure):
```python
def _norm(u): return u.lstrip('@').lower()

# in decide_action(forward branch):
sender = msg.get("from") or {}
action.sender_username = _norm(sender["username"]) if sender.get("username") else None

def is_sender_allowed(sender_username, allowed):
    if not allowed:            # empty -> no restriction
        return True
    return sender_username is not None and sender_username in allowed

# in build_jobs (forward):
if not is_sender_allowed(action.sender_username, allowed_map.get(action.source_chat_id, set())):
    return []
```
Webhook:
```python
rows = session.exec(select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()
allowed_map = defaultdict(set)
for r in rows: allowed_map[r.source_chat_id].add(r.username)
jobs = build_jobs(update, bot_row.telegram_bot_id, routes, bot_id, allowed_map)
```

## Related code files
- `webapp/app/models.py`, `forwarding.py`, `webhook.py`, `services.py` (edit)
- Tests: `webapp/tests/test_forwarding.py` (extend), `webapp/tests/test_services.py` (extend)

## Implementation Steps
1. Add `AllowedSender` model (+ table auto-created by `create_db_and_tables`).
2. Extend `Action` with `sender_username`; set it in `decide_action` (normalized).
3. Add pure `is_sender_allowed`; gate the forward branch of `build_jobs` via new `allowed_map` param.
4. Update `webhook.receive_update` to load `allowed_map` and pass it.
5. Add `services.add_allowed_sender` / `delete_allowed_sender` (+ `both_ways` helper) and cascade delete in `remove_bot`.
6. Tests (no mocks): pure `is_sender_allowed` (empty=allow, match, no-username-blocked, case-insensitive); `build_jobs` with/without allowlist; services CRUD + normalization + dedup on real SQLite.

## Todo list
- [ ] AllowedSender model
- [ ] Action.sender_username + normalization in decide_action
- [ ] is_sender_allowed (pure) + build_jobs allowed_map gate
- [ ] webhook loads allowed_map
- [ ] services add/delete + both_ways + cascade in remove_bot
- [ ] tests green (pure + services)

## Success Criteria
- With a group's list empty → forwarding unchanged (all senders).
- With `["alice"]` on group A → only messages from @Alice/@alice in A are forwarded; others (incl. no-username) dropped; other groups unaffected.
- `/chatid` still replies regardless of allowlist.
- Case/`@` variations match; duplicates deduped; deleting the last entry restores allow-all.

## Risk Assessment
- **Low/Medium**: forgetting to pass `allowed_map` → filter silently inert; covered by build_jobs tests.
- Normalization mismatch (stored vs compared) → central `_norm` used both on insert and compare.

## Security Considerations
- No new secrets. Usernames are not sensitive but validate input (regex `^[A-Za-z0-9_]{5,32}$` after stripping `@`) to avoid junk rows.
- Default-deny for missing username when a list is set (safe: only explicitly named users pass).

## Next steps
Proceed to [Phase 02](phase-02-ui-docs.md) — admin UI to manage the per-group allowlist + docs.
