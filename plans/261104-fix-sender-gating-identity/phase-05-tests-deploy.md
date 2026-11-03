# Phase 05 — Tests + deploy both VPS

## Context links
- Parent: [plan.md](./plan.md) · Depends on: Phase 02, 03, 04

## Overview
- Date: 2026-11-04
- Description: Real (no-mock) unit/integration tests for user_id gating, self-heal, backfill, and add-by-profile; then deploy to both sites and verify no-username members forward.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Decision layer is pure → test `is_sender_allowed`/`build_jobs` directly with dict updates, no Telegram calls (matches existing test_forwarding.py style — CLAUDE.md: no mock/fake data, test real logic).
- Migration/backfill testable against a real temp SQLite DB (existing db.py pattern).

## Requirements — test cases (all real)
- Gate: member with user_id in allowed_ids, NO username → **forwarded**.
- Gate: username-only match (NULL stored id) → forwarded (fallback).
- Gate: unassigned group → everyone forwarded; empty allowlist → everyone forwarded.
- Gate: non-whitelisted member under active gate → dropped.
- Gate: `from.id == 1087968824` (GroupAnonymousBot) under active gate → dropped (not auto-allowed).
- Self-heal: username-matched sender with NULL stored id → row's `telegram_user_id` persisted; next message with changed username still forwards by id.
- Backfill: AllowedSender.username matching a single SenderProfile → user_id filled; multi-match or NULL username → left NULL; 2nd run no-op.
- Add-by-profile: no-username profile → AllowedSender with user_id + NULL username created; dedupe by user_id; assign to group → forwards.

## Architecture / commands
```bash
cd webapp
pytest -q                      # all green, incl. new tests + existing 158
```
Deploy (per VPS, in `~/bot-forward/webapp`):
```bash
git pull && docker compose up -d --build
docker compose logs --tail=30 | grep -iE "timezone|typeError|Traceback" ; echo DONE
```
Verify: send a message from a whitelisted member WITHOUT a username → forwards; `POST .../copyMessage 200 OK` in logs.

## Related code files
- `webapp/tests/test_forwarding.py` (gate cases), `webapp/tests/test_services.py` (self-heal, add-by-profile, backfill), maybe new `test_sender_identity.py`.

## Implementation Steps
1. Write tests (fail first). 2. Confirm Phases 02-04 make them pass. 3. `pytest` all green. 4. Commit (conventional). 5. Deploy VPS 26 + VPS 191. 6. Live-verify no-username forward.

## Todo list
- [ ] all gate/self-heal/backfill/add-by-profile tests pass
- [ ] existing 158 tests still pass
- [ ] committed + pushed
- [ ] deployed VPS 26 + VPS 191, logs clean
- [ ] live: no-username whitelisted member forwards

## Success Criteria
- Green suite; both sites forward messages from whitelisted members regardless of whether they have a @username; no regression for existing allowlists.

## Risk Assessment
- Low once tests pass. Hot-path change is covered by pure-function tests + default-open fallback.

## Security Considerations
- Confirm anonymous/bot sender ids never pass an active gate. HTTPS deploy unchanged.

## Next steps
Close the plan. Optional hardening: pin library versions in requirements.txt (prevent SQLModel auto-upgrade breakage like the datetime incident).
