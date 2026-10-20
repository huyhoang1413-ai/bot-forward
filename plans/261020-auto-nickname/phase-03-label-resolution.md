# Phase 03 — Label resolution + build_jobs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01, phase-02
- Research: [researcher-02-capture-storage.md](./research/researcher-02-capture-storage.md) §4

## Overview
- Date: 2026-10-20
- Description: Resolve the effective `[label]` for each message (manual username-label > profile override > captured first_name when auto_nick) and feed it to build_jobs, which now takes a single resolved label instead of a username→label map.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Labeling is per-message-sender → a single resolved `label` is cleaner than a map.
- Profile lookup only when `auto_nick` ON and no manual label → ≤1 added query on the hot path.
- `build_labeled_jobs` already handles any `[name]` (unicode/emoji) via UTF-16 entity shifting.

## Requirements
- `services.resolve_label(session, bot, sender_username, sender_user_id, manual_label) -> str|None`.
- `build_jobs(...)` signature: `label: str | None = None` replaces `label_map`.
- Webhook computes the label and passes it; gating (`allowed_by_source`/`gate_active`) unchanged.

## Architecture
```python
# services.resolve_label
def resolve_label(session, bot, sender_username, sender_user_id, manual_label):
    if manual_label:                      # existing AllowedSender.label (by username)
        return manual_label
    if not bot.auto_nick or sender_user_id is None:
        return None
    prof = session.exec(select(SenderProfile).where(
        SenderProfile.bot_id == bot.id,
        SenderProfile.telegram_user_id == sender_user_id)).first()
    if not prof:
        return None
    return prof.label_override or prof.first_name

# webhook (forward branch): build label_map for MANUAL labels as today, then
manual = label_map.get(action.sender_username)
label = services.resolve_label(session, bot_row, action.sender_username,
                               action.sender_user_id, manual)
jobs = build_jobs(update, tg_id, routes, bot_id, allowed_by_source, label=label,
                  gate_active=gate_active)
```
```python
# forwarding.build_jobs — drop label_map, add label
def build_jobs(update, telegram_bot_id, routes, bot_id,
               allowed_by_source=None, label=None, gate_active=False):
    ...
    # (gating unchanged)
    for dest, dest_thread in select_destinations(...):
        if label:
            jobs.extend(build_labeled_jobs(msg, dest, bot_id, src, mid, label, dest_thread))
        else:
            jobs.append(_copy_job(..., dest_thread))
```
`label` must be sanitized to the existing label rules for forwarding safety: strip `[`,`]`,
newlines and clamp to 32 chars (first_name can contain anything). Add `sanitize_label(name)` in
forwarding and apply in resolve_label (or in build_labeled_jobs) so a weird first_name can't break
the `[..]` prefix. (Manual labels already validated by is_valid_label.)

## Related code files
- `webapp/app/services.py` — `resolve_label` + `sanitize_label` (or in forwarding).
- `webapp/app/forwarding.py` — build_jobs `label` param; `sanitize_label`.
- `webapp/app/webhook.py` — build manual label_map, resolve, pass `label`.

## Implementation Steps
1. forwarding: `sanitize_label`; build_jobs `label` param (remove label_map).
2. services: `resolve_label`.
3. webhook: resolve + pass label.
4. Tests: precedence (manual > override > first_name); auto_nick off → None; sanitize strips `[]`/
   newlines + clamps 32; labeled job carries the name; non-forum + existing manual labels unchanged.

## Todo list
- [ ] sanitize_label + build_jobs label param
- [ ] resolve_label (precedence + profile query gating)
- [ ] webhook wiring
- [ ] unit + webhook tests

## Success Criteria
- auto_nick ON, no manual label, captured "Nguyễn" → message forwarded as `[Nguyễn] ...`.
- Manual username-label still wins; override beats captured name.
- auto_nick OFF → behaves exactly like today (manual labels only).
- A first_name with `[`/`]`/emoji/41 chars → safe, clamped prefix (no broken entities).

## Risk Assessment
- Medium. Signature change (label_map→label) touches build_jobs + all its tests. Grep every
  build_jobs/label_map call site. Keep the pure layer fully covered.

## Security Considerations
- Sanitize untrusted first_name before putting it in the `[..]` prefix (injection into entities/
  formatting). Clamp length. No HTML (Telegram entities are structured, not HTML).

## Next steps
Phase 04 exposes the toggle + captured-names management.
