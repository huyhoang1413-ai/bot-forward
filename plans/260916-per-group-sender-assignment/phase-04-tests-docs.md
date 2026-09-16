# Phase 04 — Tests + Docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..03
- Project rule: real DB, NO mocks/fake data.

## Overview
- Date: 2026-09-16
- Description: Cover the new decision tree, migration backfill, services (replace-all + cascade), UI POST, and IDOR; update the existing forwarding/services/UI tests changed by the new signatures; refresh README.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- Existing 75 tests must stay green; the ones touching `build_jobs`/`add_allowed_sender` signatures already changed in commit 7b1b303 and change again here (source-aware).
- Decision-tree tests belong in `test_forwarding.py` (pure). DB/behavior tests use the real sqlite temp DB from `conftest.py`.

## Requirements
- New/updated tests all pass; total suite green.
- Backfill test proves backward-compat (no behavior change post-migration).

## Architecture / Test matrix
`test_forwarding.py` (pure `build_jobs`):
- gate_active False → forward everyone (labeled sender still gets `[label]` via label_map).
- Restricted group (`allowed_by_source={10:{"alice":None}}`, gate_active True): alice→fwd, bob→drop, no-username→drop.
- Open group while gate_active (source 11 absent from map): bob→fwd.
- Label in open group: label_map has `{"alice":"Doby"}`, source open → alice fwd WITH `[Doby]`.
- Restricted group with label: alice assigned + labeled → labeled job.

`test_migration.py` (new, real DB):
- Seed bot + 2 senders (global rows) + routes to 2 groups; run `_backfill_group_sender_assignments()`; assert 4 assignment rows; run again → still 4 (idempotent).

`test_services.py` (extend):
- `set_group_senders` replace-all: set {a}, then {a,b}, then {} → rows reflect each; bot-scoped (foreign sender_id ignored); non-source source_chat_id → no-op.
- `delete_allowed_sender` cascades assignment rows.
- `remove_bot` deletes assignments.
- `delete_route` last-route cleanup removes that source's assignments.

`test_ui_group_senders.py` (new, TestClient, real DB):
- login → create bot+route+sender → POST `/bots/{id}/groups/{src}/senders` with `sender_ids` → assignment persisted; empty POST clears; requires login (302→/login); cross-bot sender_id ignored.

Update `test_webhook.py` only if it now needs `SenderGroupAssignment` (secret tests unaffected).

## Related code files
- `webapp/tests/test_forwarding.py` (update), `test_services.py` (extend)
- `webapp/tests/test_migration.py` (new), `test_ui_group_senders.py` (new)
- `webapp/README.md`, `docs/project-roadmap.md` (note per-group assignment)

## Implementation Steps
1. Update `test_forwarding.py` build_jobs calls to new signature + add tree cases.
2. Add `test_migration.py`, extend `test_services.py`, add `test_ui_group_senders.py`.
3. Update README section "Người gửi được forward" to describe per-group assignment; roadmap bullet.
4. `pytest -q` → all green.

## Todo list
- [ ] forwarding tree tests
- [ ] migration backfill test
- [ ] services replace-all + cascade tests
- [ ] UI POST + IDOR tests
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green (existing + new).
- Backfill test demonstrates zero behavior change.
- IDOR test proves cross-bot writes are rejected.

## Risk Assessment
- Low. Mostly additive tests. Watch for the empty-set trap (assert open group forwards everyone, restricted group blocks).

## Security Considerations
- Tests explicitly assert IDOR scoping (foreign sender_ids, wrong bot) and login-required on the new endpoint.

## Next steps
Ready to implement (await user approval of plan + open questions in plan.md).
