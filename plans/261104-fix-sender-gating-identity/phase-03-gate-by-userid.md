# Phase 03 — Gate by user_id OR username (core fix) + self-heal

## Context links
- Parent: [plan.md](./plan.md) · Depends on: Phase 02 · Research: [research/researcher-01-telegram-identity.md](./research/researcher-01-telegram-identity.md)

## Overview
- Date: 2026-11-04
- Description: Change the gate so a sender passes when their stable `telegram_user_id` is in the group's allowed set, OR (fallback) their `@username` matches. Self-heal: when a username-matched sender arrives with a known id, store it on the allowlist row so it keeps working if they later drop their username.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- `decide_action` already provides `sender_user_id` — [forwarding.py:243](../../webapp/app/forwarding.py#L243). The gate just doesn't use it.
- `allowed_by_source` is built in [webhook.py:49-62](../../webapp/app/webhook.py#L49-L62). It must now carry user_ids too, not only usernames.
- Anonymous admins / channel senders: `from.id` is GroupAnonymousBot (1087968824) or `from` absent → these are NOT real members; keep current behavior (blocked under an active gate). Do NOT whitelist 1087968824. (researcher-01)

## Requirements
- Gate passes if `sender_user_id in allowed_ids` OR `sender_username in allowed_usernames`.
- Unassigned group still = open; empty allowlist still = forward everyone (unchanged).
- Self-heal: username-matched sender with NULL stored id → learn + persist their user_id.

## Architecture
`forwarding.py` — generalize the gate set to carry both keys. Change `build_jobs` gate block ([forwarding.py:338-344](../../webapp/app/forwarding.py#L338-L344)) + `is_sender_allowed`:
```python
def is_sender_allowed(sender_username, sender_user_id, allowed_usernames, allowed_ids) -> bool:
    if not allowed_usernames and not allowed_ids:
        return True  # open
    if sender_user_id is not None and sender_user_id in allowed_ids:
        return True
    return sender_username is not None and sender_username in allowed_usernames
```
`webhook.py` — build per-source `{usernames}` and `{user_ids}` from the same JOIN (AllowedSender now has `telegram_user_id`); pass both into `build_jobs` (extend its signature / pass a small struct). Keep the "absent source ⇒ open" rule.

`services.py` (self-heal, called in the webhook forward branch) — when the sender was allowed via username and the matched AllowedSender row has `telegram_user_id IS NULL`, set it to `action.sender_user_id`:
```python
def learn_sender_user_id(session, bot_id, username, user_id) -> None:
    if not username or user_id is None: return
    row = session.exec(select(AllowedSender).where(
        AllowedSender.bot_id==bot_id, AllowedSender.username==username,
        AllowedSender.telegram_user_id.is_(None))).first()
    if row: row.telegram_user_id = user_id; session.add(row); session.commit()
```

## Related code files
- `webapp/app/forwarding.py` (`is_sender_allowed`, `build_jobs` gate + signature), `webapp/app/webhook.py` (build id+username sets, call learn_sender_user_id), `webapp/app/services.py` (`learn_sender_user_id`).

## Implementation Steps
1. Update `is_sender_allowed` signature + logic. 2. Update `build_jobs` gate to use both sets (keep open-group semantics). 3. Build `allowed_ids_by_source` + `allowed_usernames_by_source` in webhook. 4. Add + call `learn_sender_user_id` in the forward branch. 5. Update all `build_jobs`/`is_sender_allowed` call sites + tests.

## Todo list
- [ ] gate passes by user_id
- [ ] username fallback preserved
- [ ] open-group / empty-allowlist semantics unchanged
- [ ] self-heal persists user_id from live traffic
- [ ] GroupAnonymousBot (1087968824) / no-`from` still blocked under active gate

## Success Criteria
- A whitelisted member with NO username but a known user_id forwards. A username-matched member keeps forwarding and gains a stored user_id. Non-whitelisted members still blocked where a gate is active.

## Risk Assessment
- Medium (touches the hot path). Mitigate: pure-function unit tests for every branch (Phase 05); default-open semantics mean a bug fails toward forwarding, not silent drop. Keep change minimal.

## Security Considerations
- Never auto-whitelist anonymous/bot sender ids. user_id match must be exact int compare (no coercion).

## Next steps
Phase 04: let admins whitelist no-username members via captured profiles.
