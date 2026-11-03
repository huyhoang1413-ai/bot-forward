# Phase 03 — Neutralize the hidden-gate foot-gun

## Context links
- Parent: [plan.md](./plan.md) · Depends on: none (independent) · Related incident: plan 261104-fix-sender-gating-identity Phase 01

## Overview
- Date: 2026-11-04
- Description: Stop `_backfill_group_sender_assignments` from auto-creating per-group gate assignments. That migration is the ONLY path that ever turned nickname-list entries into hidden forwarding gates — the cause of "chỉ 1 người forward". After this, the ONLY way a group becomes gated is an explicit add in section 3.
- Priority: Medium · Implementation status: Not started · Review status: Pending

## Key Insights
- `_backfill_group_sender_assignments` ([db.py:124-157](../../webapp/app/db.py#L124-L157)) assigns every global sender to every source group on startup. Intent back then: "allowlist applies to all groups". Under the new model (section 1 = nickname, not gate) this is WRONG — it silently gates every group that has any global sender.
- It already ran on both VPS. Going forward it re-runs for any NEW (sender, group) pair → keeps re-introducing hidden gates. Must be stopped.
- Making it a no-op is safe: existing assignments stay (clean them via the other plan's Phase 01 if unwanted); no NEW auto-gates get created.

## Requirements
- No new deployment auto-gates a group from the nickname list.
- Existing data untouched by this change (cleanup is a separate, explicit op).
- Adding a nickname in section 1 never creates an assignment (already true — verify).

## Architecture
Option A (recommended, KISS): turn the migration into a no-op and stop calling it.
```python
# db.py create_db_and_tables(): remove the _backfill_group_sender_assignments() call.
# Keep the function but short-circuit (return) + a comment explaining why, so historical
# DBs don't get NEW auto-assignments. Do NOT delete existing rows here.
```
Option B: keep it but only run ONCE ever (guard with a migration-marker row). More code; not needed. → choose A.
- Verify `add_allowed_sender` / the section-1 add route create NO SenderGroupAssignment (confirmed [services.py:231-266](../../webapp/app/services.py#L231-L266)).

## Related code files
- `webapp/app/db.py` (`create_db_and_tables`, `_backfill_group_sender_assignments`).

## Implementation Steps
1. Remove the call from `create_db_and_tables()`. 2. Short-circuit the function body with an explanatory comment (leave for history). 3. Confirm no other caller. 4. Note in release notes: to open already-gated groups, run the cleanup (other plan, Phase 01).

## Todo list
- [ ] `_backfill_group_sender_assignments` no longer auto-creates assignments
- [ ] no other caller
- [ ] section-1 add verified to create no assignment
- [ ] existing rows untouched by the code change

## Success Criteria
- A freshly deployed/updated bot: putting people in the nickname list does NOT restrict forwarding; groups stay open until section 3 is used.

## Risk Assessment
- Low. Only removes a surprising auto-gate. Deployments relying on "global list = gate all groups" are exactly the buggy behavior we're removing; the correct way is section 3.

## Security Considerations
- Removing auto-gate widens defaults toward "forward everyone" — acceptable + matches stated spec; explicit gating still available per route.

## Next steps
Phase 04: tests + deploy.
