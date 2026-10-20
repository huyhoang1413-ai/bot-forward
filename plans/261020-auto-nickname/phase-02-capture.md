# Phase 02 — Capture sender name (once)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01
- Research: [researcher-01-sender-identity.md](./research/researcher-01-sender-identity.md),
  [researcher-02-capture-storage.md](./research/researcher-02-capture-storage.md)

## Overview
- Date: 2026-10-20
- Description: Extract the sender's user_id + first_name and store it once per (bot, user). Cheap: on-conflict-do-nothing + a per-process seen-cache. Captures regardless of auto_nick (so toggling on works retroactively).
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Only capture when `from` exists (real user). Anonymous/channel/auto-forward → `from` absent → skip.
- Capture-once = never overwrite `first_name`; `username` may refresh.
- Seen-cache removes ~all repeat writes; a process restart costs one harmless no-op upsert per user.

## Requirements
- `decide_action` also returns `sender_user_id: int | None`, `sender_first_name: str | None`.
- `services.capture_sender(session, bot_id, user_id, first_name, username)` — on_conflict_do_nothing;
  guarded by a module-level `set` cache keyed (bot_id, user_id).
- Webhook calls it for forward actions with a real sender.

## Architecture
```python
# forwarding.decide_action  (forward branch)
frm = msg.get("from") or {}
return Action("forward", ..., sender_user_id=frm.get("id"),
              sender_first_name=frm.get("first_name"))

# services.py
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
_captured: set[tuple[int, int]] = set()

def capture_sender(session, bot_id, user_id, first_name, username=None):
    if user_id is None or not first_name:
        return
    key = (bot_id, user_id)
    if key in _captured:
        return
    stmt = sqlite_insert(SenderProfile).values(
        bot_id=bot_id, telegram_user_id=user_id,
        first_name=first_name, username=username,
    ).on_conflict_do_nothing(index_elements=["bot_id", "telegram_user_id"])
    session.exec(stmt)            # or session.execute(stmt)
    # optionally refresh username when changed (UPDATE ... WHERE username != ...)
    session.commit()
    _captured.add(key)
```
Webhook (after `decide_action`, forward branch only):
```python
action = decide_action(update, bot_row.telegram_bot_id)
if action.kind == "forward":
    services.capture_sender(session, bot_id, action.sender_user_id,
                            action.sender_first_name, action.sender_username)
```
`_captured` is a simple unbounded set (≈16B/entry → fine for thousands). Note in docs it's
process-local (not shared across replicas) — acceptable (on_conflict makes duplicates harmless).

## Related code files
- `webapp/app/forwarding.py` — Action fields + decide_action extraction.
- `webapp/app/services.py` — `capture_sender` + cache + SenderProfile import.
- `webapp/app/webhook.py` — call capture_sender on forward.

## Implementation Steps
1. Add Action.sender_user_id/sender_first_name + decide_action extraction.
2. services.capture_sender (on_conflict_do_nothing + cache).
3. webhook calls it.
4. Tests: capture inserts once; second message no-op; no `from` → skip; cache hit skips DB.

## Todo list
- [ ] decide_action user_id + first_name
- [ ] capture_sender (on_conflict + seen-cache)
- [ ] webhook capture call
- [ ] capture tests

## Success Criteria
- First message from a user → one SenderProfile row with their first_name.
- Repeat messages → no duplicate, name unchanged (capture-once).
- Anonymous/channel message (no `from`) → no row.

## Risk Assessment
- Low. `session.exec` vs `session.execute` for a Core insert — use the form SQLModel supports
  (`session.exec(stmt)` works for selects; for a dialect insert use `session.execute(stmt)` +
  commit). Verify in impl.
- Cache is per-process; fine for a single container (current deploy).

## Security Considerations
- Stores first_name + username (already visible to the bot). Per-bot scoped. No PII beyond what
  Telegram already exposes to the bot.

## Next steps
Phase 03 turns captured names into forward labels.
