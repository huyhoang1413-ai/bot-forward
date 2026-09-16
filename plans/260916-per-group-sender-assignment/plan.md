# Plan: Global list + per-group sender assignment

Date: 2026-09-16 · Status: Implemented (all 4 phases, 89 tests pass) · Priority: High

## Goal
Keep declaring each sender+nickname ONCE globally per bot, but choose WHICH senders apply
to WHICH source group (on/off per group). Backward-compatible with today's global-per-bot
allowlist (commit 7b1b303).

## Locked design (reconciled from research-01 + research-02)
- Schema = **junction table** (`SenderGroupAssignment`), NOT a JSON column. `AllowedSender`
  stays unchanged (keep `source_chat_id=GLOBAL_SOURCE` column & constraint — additive-only).
- Migration = additive: `create_all()` + one-time idempotent backfill in `db.py` assigning
  each existing `AllowedSender` to EVERY distinct `Route.source_chat_id` of its bot (preserves
  current behavior). Called after the existing collapse migration.
- Forwarding: zero AllowedSender rows for a bot → forward everyone (legacy). Else per source
  group: ≥1 assignment → only those; zero assignments → open (forward everyone that group).
  Labels decouple from gating: apply `[label]` to any forwarded msg whose sender has a label.
- UX: per-group `<details>` checkbox `<fieldset>` in the "Tuyến forward" card. POST replace-all
  `sender_ids` for that group. Plain HTML, no JS.

## Phases (each independently testable)
1. **phase-01-model-migration.md** — `SenderGroupAssignment` model + indexes/constraints;
   idempotent backfill `_backfill_group_sender_assignments()` in `db.py`.
2. **phase-02-forwarding-webhook.md** — new source-aware `build_jobs` signature + gating/label
   decision tree (pure); webhook builds `allowed_by_source`, `label_map`, `gate_active` in 2 queries.
3. **phase-03-services-ui-template.md** — `set_group_senders()` (replace-all, bot-scoped) +
   cascade cleanup in `delete_allowed_sender`/`remove_bot`/`delete_route`; new UI endpoint +
   `bot_detail` context + template checkbox form.
4. **phase-04-tests-docs.md** — real-DB tests for decision tree, backfill, services cascade,
   UI POST, IDOR; update the existing tests that change; docs/README.

## Key files
- `webapp/app/models.py`, `db.py`, `forwarding.py`, `webhook.py`, `services.py`, `ui.py`
- `webapp/app/templates/bot_detail.html`
- `webapp/tests/` (75 existing tests must stay green; a few change — see phase-04)

## Backward-compat guarantee
Post-migration every existing (sender × group) pair has an assignment, so gating is identical
to today. New table empty for a fresh bot with no senders → still "forward everyone".

## Open questions / decisions for reviewer
1. **Zero-assignment semantics after user unchecks all in a group.** Recommended (this design):
   "forward everyone". There is NO way to express "forward nobody for this group" — the empty
   set is overloaded as "open". If the user actually wants "mute this group", we'd need an
   explicit flag/sentinel (out of scope). Flagging for decision.
2. **"Assign to all groups" affordance on the global card.** Deferred as YAGNI. Confirm defer,
   or request a one-click "apply to every group" button per sender in phase-03.
3. **Per-group label override.** Deferred (research-02 §5). Schema leaves room (add
   `label_override` to junction later) but not implemented now.
4. **`delete_route` cascade of last-route-in-group assignments.** Planned as best-effort cleanup
   in phase-03; confirm whether stale assignments for a vanished source group are acceptable
   (harmless — they just never match) vs. must-clean.
