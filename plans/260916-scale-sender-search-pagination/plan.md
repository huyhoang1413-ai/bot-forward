# Plan: Scale sender allowlist to 500-1000 (search + pagination)

Date: 2026-09-16 · Status: Implemented (4 phases, 101 tests pass) · Priority: High

## Problem
The per-group checkbox UI renders EVERY sender inside EVERY group block → thousands of
checkboxes with 500-1000 senders → page unusable. The global registry card also renders all
rows. The **data model (junction `SenderGroupAssignment`) already scales**; only the UI +
a couple of queries/indexes need to change.

## Chosen approach (from research 01 + 02)
Keep the junction model. Replace "render-all" UI with **server-side search + pagination** and
**incremental add/remove**, on **dedicated manager pages** (minimal JS):
- Registry manager: `/bots/{id}/senders` — search + paginate + add + edit nickname + remove.
- Per-group manager: `/bots/{id}/groups/{source}/senders` — search picker (registry senders
  NOT yet assigned) + paginated assigned list + add/remove one at a time.
- `bot_detail` shows only per-group counts + "Quản lý người gửi" links (no tables/checkboxes).
- Backend: prefix search `username.startswith(q)` on an additive `COLLATE NOCASE` index; offset
  pagination (≤1000 rows); incremental `add_group_sender`/`remove_group_sender`; webhook hot
  path becomes a **single LEFT JOIN** (drops the 1000-id IN-list, sidesteps SQLite param limit).

## Semantics (UNCHANGED — keep current behavior)
- Bot has 0 senders → forward everyone. Group with ≥1 assignment → only those. Group with 0
  assignments → forward everyone (open). Labels decouple from gating.
  (Note: research-02 §5 mislabeled "group empty = all global senders"; correct = forward everyone.)

## Phases (each independently testable)
1. **phase-01-backend-query-index.md** — additive `COLLATE NOCASE` index; single-JOIN webhook;
   service helpers (search/paginate, list group senders, unassigned picker, incremental add/remove).
2. **phase-02-registry-page.md** — `/bots/{id}/senders` page + template; slim the bot_detail
   registry card to count+link; keep add/edit/delete via search-paginated view.
3. **phase-03-per-group-page.md** — `/bots/{id}/groups/{source}/senders` page + template;
   slim each bot_detail group block to count+link; retire the checkbox `set_group_senders` form.
4. **phase-04-tests-docs.md** — real-DB tests (search, pagination, incremental add/remove, IDOR,
   single-JOIN webhook, index migration); update changed tests; README + roadmap.

## Key files
- `webapp/app/db.py` (index migration), `webhook.py` (single JOIN), `services.py` (helpers),
  `ui.py` (new routes), `templates/` (2 new: senders.html, group_senders.html; edit bot_detail.html)
- `webapp/tests/` (89 green now; some change — see phase-04)

## Defaults (change if reviewer disagrees)
- page_size = 50 · search = username **prefix** only (nickname search deferred) · remove via
  browser `confirm()` (minimal JS) · two-column desktop / stacked mobile.

## Open questions / decisions for reviewer
1. **Search scope:** username prefix only (fast, index-backed) vs also search nickname/label
   (substring → slower, no index). MVP = username prefix. Add nickname search?
2. **Pagination size:** 50/page — OK?
3. **CSV/bulk import + JS typeahead:** deferred (research §8). Confirm defer.
4. **Registry page vs keep inline:** plan uses a dedicated `/bots/{id}/senders` page. OK?
