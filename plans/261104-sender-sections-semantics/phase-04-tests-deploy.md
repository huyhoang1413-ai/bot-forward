# Phase 04 — Tests + deploy both VPS

## Context links
- Parent: [plan.md](./plan.md) · Depends on: Phase 01, 02, 03

## Overview
- Date: 2026-11-04
- Description: Real (no-mock) tests that lock the 3 rules + the first-token auto-nick + the no-auto-gate guarantee; then deploy both sites.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- Decision layer + helpers are pure → test directly with dict updates / real temp SQLite (matches existing test_forwarding.py, test_services.py). CLAUDE.md: test real logic, no mocks.

## Requirements — test cases (all real)
- `first_token`: "Minh Anh"→"Minh"; "Antony"→"Antony"; "  "→None/fallback; emoji-only→fallback; None→None.
- `resolve_label`: auto path trims to first token; manual label returned verbatim (even multi-word); `label_override` verbatim; auto_nick off → None.
- Gate (unchanged, regression): unassigned group → everyone; add-to-section-3 → only those; empty allowlist → everyone.
- Section 1 add (`add_allowed_sender`): creates NO SenderGroupAssignment (nickname ≠ gate).
- Migration: `_backfill_group_sender_assignments` no longer creates assignments (call removed / no-op); existing rows untouched.

## Architecture / commands
```bash
cd webapp && pytest -q          # new + existing 158 all green
```
Deploy (each VPS, ~/bot-forward/webapp):
```bash
git pull && docker compose up -d --build
docker compose logs --tail=30 | grep -iE "timezone|typeError|Traceback"; echo DONE
```
Verify in panel: section wording reads clearly; toggle auto-nick → forwarded messages show `[FirstToken] ...`; a group with no section-3 entries forwards everyone.

## Related code files
- `webapp/tests/test_forwarding.py` (first_token, gate regression), `webapp/tests/test_services.py` (resolve_label, add_allowed_sender no-assignment), `webapp/tests/` migration test.

## Implementation Steps
1. Write tests (fail first). 2. Implement Phases 01–03 to green. 3. Full `pytest`. 4. Commit (conventional). 5. Deploy VPS 26 + 191. 6. Live-verify wording + auto-nick + open-group.

## Todo list
- [ ] first_token + resolve_label tests pass
- [ ] gate regression tests pass
- [ ] nickname-add-creates-no-gate test passes
- [ ] existing 158 tests pass
- [ ] committed + pushed + deployed both VPS, logs clean
- [ ] live: auto-nick shows first token; open group forwards everyone

## Success Criteria
- Green suite; UI matches the 3 rules; no regression; both sites updated.

## Risk Assessment
- Low once tests pass.

## Security Considerations
- `sanitize_label` downstream unchanged. HTTPS deploy unchanged.

## Next steps
Close plan. Optional: pin requirements.txt versions (prevent library auto-upgrade breakage).
