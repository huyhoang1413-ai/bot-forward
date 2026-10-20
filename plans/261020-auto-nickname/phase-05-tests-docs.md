# Phase 05 — End-to-end tests + docs

## Context links
- Parent: [plan.md](./plan.md) · Depends on: phase-01..04
- Project rule: real DB, NO mocks.

## Overview
- Date: 2026-10-20
- Description: Prove auto-nick end-to-end (capture → label on forward), precedence, off-state, sanitization; update README + roadmap.
- Priority: High
- Implementation status: Not started
- Review status: Pending

## Key Insights
- The pure label-resolution + build_jobs changes carry most risk → cover hardest in test_forwarding.
- Webhook integration test asserts real ForwardJob rows (no network), like test_webhook_query.py.

## Requirements
- Full suite green; auto-nick behavior covered; existing behavior unchanged when auto_nick off.

## Architecture / Test matrix
`test_forwarding.py` (update + extend):
- build_jobs `label` param: `label="Nguyễn"` → labeled job `[Nguyễn] ...`; `label=None` → plain copy.
- sanitize_label: strips `[` `]` `\n`, clamps 32, keeps unicode/emoji.
- update every build_jobs/label_map call site to the new `label=` signature.

`test_services.py` (extend):
- `capture_sender`: inserts once; second call no-op (cache + on_conflict); None user_id/first_name → skip.
- `resolve_label`: manual label wins; override beats first_name; first_name used only when auto_nick;
  off → None; no profile → None.
- profile list/search/override/delete + set_auto_nick.

`test_webhook_auto_nick.py` (new, real DB):
- Seed bot (auto_nick=True) + a route, no allowlist. POST a message from user id 5 first_name "Nguyễn"
  → SenderProfile row created AND ForwardJob is a labeled `[Nguyễn]` delivery.
- Second message same user → still `[Nguyễn]`, no duplicate profile.
- auto_nick=False → ForwardJob is a plain copy (no label).
- Message with no `from` (sender_chat only) → no profile, plain forward.

`test_ui` (extend): auto-nick toggle persists; names page list/search/override/delete; cross-team 403.

## Related code files
- `webapp/tests/test_forwarding.py`, `test_services.py`, UI tests (update/extend)
- new: `webapp/tests/test_webhook_auto_nick.py`
- `webapp/README.md`, `docs/project-roadmap.md`

## Implementation Steps
1. Update forwarding tests to the `label=` signature + sanitize cases.
2. Add capture/resolve service tests.
3. Add webhook auto-nick e2e test.
4. UI tests.
5. README "Nickname tự động" section + roadmap bullet.
6. `pytest -q` green.

## Todo list
- [ ] forwarding tests (label param + sanitize)
- [ ] services tests (capture + resolve + profile CRUD)
- [ ] webhook e2e auto-nick test
- [ ] UI tests
- [ ] README + roadmap

## Success Criteria
- `pytest -q` fully green.
- E2e: auto_nick on → first message from a user forwards as `[first_name] ...`; off → unchanged.
- Capture-once + precedence + sanitize all asserted.

## Risk Assessment
- Low (tests/docs). Main risk: missing a build_jobs call site in the signature migration.

## Security Considerations
- The sanitize test IS the injection-safety gate for untrusted first_names.

## Next steps
Deploy: `git pull && docker compose up -d --build`. Per bot: toggle "Tự động gắn tên người gửi";
names populate as people post; edit overrides on the "Tên đã ghi nhận" page.
