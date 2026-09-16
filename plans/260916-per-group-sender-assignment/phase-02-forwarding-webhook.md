# Phase 02 — Forwarding + Webhook (source-aware gating)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01 (table exists)
- Research: [researcher-02-ux-semantics.md](./research/researcher-02-ux-semantics.md) §2

## Overview
- Date: 2026-09-16
- Description: Make `build_jobs` source-aware: gate each message by the senders assigned to its source group, while labels stay decoupled (apply to any known sender). Webhook builds the lookup structures in ≤2 queries.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Today `build_jobs(...)` takes one global `allowed_senders` map and gates every group identically. Now gating depends on `action.source_chat_id`.
- Keep the decision layer PURE (no DB/network) for unit tests. Webhook prepares data; `build_jobs` only reads it.
- Decouple labels from gating so `[label]` still shows in "open" groups.

## Requirements
- Backward-compatible decision tree (see below).
- No N+1: webhook builds `allowed_by_source` + `label_map` + `gate_active` with ≤2 queries.
- All existing forwarding tests updated to new signature; new tree cases covered (phase-04).

## Architecture
New signature:
```python
def build_jobs(update, telegram_bot_id, routes, bot_id,
               allowed_by_source: dict[int, dict[str, str | None]] | None = None,
               label_map: dict[str, str | None] | None = None,
               gate_active: bool = False) -> list[ForwardJob]:
```
Gating/labeling tree (replaces current gate block):
```python
# forward branch, after decide_action:
src = action.source_chat_id
if gate_active:
    group_map = (allowed_by_source or {}).get(src)   # None => group has no assignment => open
    if group_map is not None:                        # restricted group
        if not is_sender_allowed(action.sender_username, set(group_map)):
            return []
    # group_map is None => open group => no gate
# gate_active False => bot has no senders => forward everyone

# label: from global label_map, regardless of gating
label = (label_map or {}).get(action.sender_username) if action.sender_username else None
```
`gate_active = (bot has ≥1 AllowedSender)`. `is_sender_allowed` unchanged (empty set => allow all — but we only call it when group_map is a non-None set; empty set can't occur because an empty assignment set is represented as absent/None). Guarantee that in webhook (only add a source key when it has ≥1 assigned sender).

Webhook build (2 queries):
```python
# Q1: senders of this bot -> label_map + id->username
senders = session.exec(select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()
gate_active = bool(senders)
label_map = {s.username: s.label for s in senders}
by_id = {s.id: s for s in senders}
# Q2: assignments joined implicitly by id membership
allowed_by_source: dict[int, dict[str, str | None]] = {}
if gate_active:
    for a in session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.allowed_sender_id.in_(list(by_id))
        )
    ).all():
        snd = by_id.get(a.allowed_sender_id)
        if snd:
            allowed_by_source.setdefault(a.source_chat_id, {})[snd.username] = snd.label
jobs = build_jobs(update, bot_row.telegram_bot_id, routes, bot_id,
                  allowed_by_source, label_map, gate_active)
```
Only groups with ≥1 assignment appear in `allowed_by_source` → absent key == open group.

## Related code files
- `webapp/app/forwarding.py` — new signature + tree; keep `is_sender_allowed`, `build_labeled_jobs` as-is.
- `webapp/app/webhook.py` — build structures, import `SenderGroupAssignment`.

## Implementation Steps
1. Update `build_jobs` signature + docstring + gate/label block.
2. Update `webhook.py` queries + call.
3. Run `pytest tests/test_forwarding.py` (will fail until phase-04 updates tests) — expected; keep signature stable.

## Todo list
- [ ] forwarding.py: signature + decision tree
- [ ] webhook.py: 2-query build + call
- [ ] sanity: labels still apply in open group

## Success Criteria
- gate_active False → everyone forwarded (labels still applied if sender labeled).
- Restricted group (in `allowed_by_source`) → only listed usernames; others dropped; no-username dropped.
- Open group (absent key) while gate_active → everyone forwarded.
- One update → ≤2 DB queries in webhook; no per-dest query.

## Risk Assessment
- Medium: signature change ripples to tests. Mitigate: land phase-02 + phase-04 together.
- Empty-set trap: ensure webhook never inserts an empty dict for a source (would wrongly block all). Guaranteed by only adding on real rows.

## Security Considerations
- No new external input. Gating is fail-open only when the bot intentionally has no senders (documented legacy behavior). `.in_()` uses parameter binding (no injection).

## Next steps
Phase 03 exposes management of these assignments via services + UI.
