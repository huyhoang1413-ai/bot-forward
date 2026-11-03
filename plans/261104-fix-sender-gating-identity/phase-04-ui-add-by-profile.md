# Phase 04 — UI: whitelist a member by captured profile (user_id-first)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: Phase 02, Phase 03

## Overview
- Date: 2026-11-04
- Description: Close the loop for members WITHOUT a @username. Today the admin can only add senders by typing a username ([ui.py:402-412](../../webapp/app/ui.py#L402-L412)), so no-username members can never be whitelisted. Let the admin add an allowlist entry by picking a captured `SenderProfile` (first_name [+ @username if any]); that stores `telegram_user_id` directly.
- Priority: Medium · Implementation status: Not started · Review status: Pending

## Key Insights
- `SenderProfile` already lists everyone who has messaged the bot, searchable/paginated via `list_profiles` ([services.py:658](../../webapp/app/services.py#L658)); the "Quản lý Nickname" page already renders a profiles panel ([ui.py:474](../../webapp/app/ui.py#L474)).
- An allowlist row keyed by user_id need not have a username — `AllowedSender.username` could be empty for profile-added rows. Minimal change: store the profile's username if present, else a placeholder, and always set `telegram_user_id`. Gate (Phase 03) matches on id regardless.

## Requirements
- "Add to allowlist" action on each captured profile → creates/updates an AllowedSender with `telegram_user_id` = profile.telegram_user_id, `username` = profile.username (may be None), `label` default = first_name.
- Works for profiles with no username (the whole point).
- Dedupe by (bot_id, telegram_user_id).

## Architecture
`services.py`:
```python
def add_sender_from_profile(session, bot_id, telegram_user_id) -> AllowedSender | None:
    p = session.exec(select(SenderProfile).where(
        SenderProfile.bot_id==bot_id, SenderProfile.telegram_user_id==telegram_user_id)).first()
    if not p: return None
    row = session.exec(select(AllowedSender).where(
        AllowedSender.bot_id==bot_id, AllowedSender.telegram_user_id==telegram_user_id)).first()
    if row: return row
    row = AllowedSender(bot_id=bot_id, source_chat_id=GLOBAL_SOURCE,
        username=p.username or "", telegram_user_id=telegram_user_id,
        label=p.label_override or p.first_name)
    session.add(row); session.commit(); session.refresh(row); return row
```
`ui.py` — new POST `/bots/{bot_id}/profiles/{user_id}/allow` → `add_sender_from_profile` → redirect back. Template: an "➕ Cho phép forward" button per profile row in the nickname page.
- Note: relax `add_allowed_sender`'s `uq_allowed_sender` concerns — profile-added rows may share empty username; rely on the (bot_id, telegram_user_id) uniqueness in code (not a DB constraint change, to stay additive). If two empty-username rows would violate the existing unique constraint `(bot_id, source_chat_id, username)`, store `username` as `None` and confirm the constraint allows multiple NULLs (SQLite: NULLs are distinct in UNIQUE → OK).

## Related code files
- `webapp/app/services.py` (`add_sender_from_profile`), `webapp/app/ui.py` (route), `webapp/app/templates/` nickname/profiles template (button), assignment UI unchanged (assign by sender row still works).

## Implementation Steps
1. `add_sender_from_profile` service. 2. UI route + button. 3. Verify NULL-username rows don't trip `uq_allowed_sender` (use None, not ""). 4. Assign the new sender to groups via existing assignment UI.

## Todo list
- [ ] add-by-profile service (dedupe by user_id)
- [ ] UI button + route on nickname page
- [ ] no-username profile can be whitelisted + assigned
- [ ] unique-constraint safe (NULL username distinct)

## Success Criteria
- Admin can whitelist a member who has no @username, assign them to a group, and their messages forward.

## Risk Assessment
- Low-medium. Main gotcha: unique constraint on username. Use `username=None` for no-username profiles (NULLs distinct in SQLite UNIQUE). Covered by a test.

## Security Considerations
- Team/bot scoping on the new route (reuse `require_bot_access`). No IDOR: profile + allowlist both filtered by bot_id.

## Next steps
Phase 05: tests + deploy.
