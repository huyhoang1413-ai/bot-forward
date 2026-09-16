# Phase 04 — Tests + Docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..03
- Project rule: real DB, NO mocks.

## Overview
- Date: 2026-09-16
- Description: Test search/pagination, incremental add/remove, IDOR, single-JOIN webhook, and index migration; update tests broken by the UI/endpoint changes; refresh README + roadmap.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- `set_group_senders` (replace-all) is retired → `test_ui_group_senders.py` + related `test_services.py` cases must switch to the incremental endpoints/helpers.
- Existing forwarding decision-tree tests are unchanged (semantics untouched) — good regression anchor.

## Requirements
- Full suite green. New behavior covered. Backward-compat of forwarding proven unchanged.

## Architecture / Test matrix
`test_services.py` (update + extend):
- `list_senders`: seed 120 senders → page 0/1 sizes, `q` prefix filters, total correct.
- `list_group_senders` / `search_unassigned`: picker excludes assigned; assigned list filtered by source; pagination.
- `add_group_sender`: idempotent; IDOR (foreign sender_id, non-source) → no-op/False.
- `remove_group_sender`: removes only that pair; foreign bot → no-op.
- DELETE old `set_group_senders` tests (replaced).

`test_webhook_query.py` (new, real DB):
- Seed bot + senders + assignments across 2 groups; call the webhook build (or a small extracted
  helper) and assert `allowed_by_source`/`label_map`/`gate_active` equal the pre-refactor result
  using ONE query. (Or assert via `/webhook/{id}` producing correct ForwardJobs.)

`test_migration_index.py` (new):
- After `create_db_and_tables()`, `PRAGMA index_list(allowedsender)` contains `ix_allowedsender_bot_username`; idempotent on re-run.

`test_ui_senders.py` (new, TestClient):
- login → GET `/bots/{id}/senders` 200; add via POST → appears; search `?q=` filters; pagination
  `?page=1`; edit label; remove; login required.

`test_ui_group_senders.py` (rewrite):
- GET group page 200; POST `.../{sender_id}/add` assigns; picker no longer lists it; POST
  `.../{sender_id}/remove` unassigns; cross-bot sender id ignored; login required.

`test_forwarding.py` — unchanged (regression anchor). `test_webhook.py` secret tests unchanged.

## Related code files
- `webapp/tests/test_services.py`, `test_ui_group_senders.py` (rewrite), `test_ui_allowed.py`/`test_ui_labels.py` (redirect target now `/senders`)
- new: `test_ui_senders.py`, `test_webhook_query.py`, `test_migration_index.py`
- `webapp/README.md`, `docs/project-roadmap.md`

## Implementation Steps
1. Update service tests to helpers; delete replace-all cases.
2. Rewrite `test_ui_group_senders.py` to incremental endpoints.
3. Add `test_ui_senders.py`, `test_webhook_query.py`, `test_migration_index.py`.
4. Fix redirect-target assertions in `test_ui_allowed.py`/`test_ui_labels.py` if they assert `/bots/{id}`.
5. README "Người gửi" section + roadmap bullet: search/paginate + per-group manager pages.
6. `pytest -q` → all green.

## Todo list
- [ ] services tests (search/paginate/add/remove/IDOR)
- [ ] webhook single-JOIN test
- [ ] index migration test
- [ ] UI tests (senders + group senders rewrite)
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green.
- Search/pagination/add/remove all asserted on real DB (incl. a 100+ row seed for paging).
- IDOR + login-required asserted on new endpoints.

## Risk Assessment
- Low. Mostly test churn. Ensure seeds are big enough to exercise pagination (>page_size).

## Security Considerations
- Tests assert IDOR (cross-bot sender id, non-source group) and auth on all new routes.

## Next steps
Await user approval of plan + open questions in plan.md, then implement phases in order.
