# Report 01 — Root cause: why only "Antony" forwards

Date: 2026-11-04 · Scope: @WeFunForward_bot "chỉ 1 người (Antony) forward, người khác không".

## Verdict
The sender gate matches by **Telegram @username only**. Members with **no public @username** (or a changed one) are silently **blocked** whenever a source group has per-sender assignments. The one member who forwards (Antony) is the one whose live `@username` matches an allowlist entry. This is a **design fragility**, not a crash.

## Evidence (code)
- Gate is username-keyed — [forwarding.py:250-258](../../webapp/app/forwarding.py#L250-L258):
  ```python
  def is_sender_allowed(sender_username, allowed):
      if not allowed: return True
      return sender_username is not None and sender_username in allowed
  ```
  → `sender_username is None` (no @username) ⇒ **False** ⇒ dropped.
- Sender username comes straight from the update — [forwarding.py:222-223](../../webapp/app/forwarding.py#L222-L223):
  `raw_username = from_user.get("username"); sender_username = normalize(...) if raw_username else None`. Telegram usernames are **optional + mutable** (see researcher-01).
- Allowlist stores only `username`, no stable id — [models.py:89-98](../../webapp/app/models.py#L89-L98), [services.py:231-266](../../webapp/app/services.py#L231-L266).
- Gate activates for a group only when it has assignments — [forwarding.py:338-344](../../webapp/app/forwarding.py#L338-L344): `group_map = allowed_by_source.get(source)`; `None` ⇒ open (everyone), non-None ⇒ restricted to that username set.
- A **stable identity already exists but is unused by the gate**: `SenderProfile(telegram_user_id, first_name, username)` is captured for EVERY sender on first message — [services.py:586-612](../../webapp/app/services.py#L586-L612). `decide_action` already carries `sender_user_id` — [forwarding.py:243](../../webapp/app/forwarding.py#L243) — but `build_jobs`/gate ignore it.

## Two possible situations (Phase 01 disambiguates against the live DB)
1. **Intent = forward everyone** in those 2 routes, but someone created per-group assignments that restrict them → groups are over-gated. **Fix = remove the assignments (open the groups).** No code change; instant.
2. **Intent = whitelist specific people**, but some of those people have no @username / changed it → username gate can never match them. **Fix = gate by `telegram_user_id`** (reports/02).

## Confirmed facts (researchers)
- `from.id` (user_id): always present for user messages, immutable, unique, 64-bit — the canonical identity. `from.username`: optional, mutable, unreliable. (researcher-01)
- Anonymous admins / channel-as-sender: `from` is absent / is GroupAnonymousBot (id 1087968824); real identity is `sender_chat.id`. Identity gating must treat these explicitly. (researcher-01)
- Adding a nullable `telegram_user_id INTEGER` to `allowedsender` is instant + safe in SQLite; the app's `_add_missing_columns()` already does additive ALTERs idempotently; backfill via correlated subquery from `senderprofile` (guard: username non-null, single match, only when currently NULL). (researcher-02)

## Recommendation
- **Immediate**: Phase 01 — diagnose + (if intent is "everyone") open the two groups → forwarding restored now, no deploy.
- **Durable**: Phases 02-04 — add `telegram_user_id` to the allowlist, gate by **user_id OR username**, self-heal the id from live traffic + one-time backfill from `SenderProfile`, and let the admin whitelist by captured profile (so no-username members can be listed). Removes the fragility permanently.

## Unresolved questions
- For these 2 routes, does the user want **everyone** or **specific people**? (Decides whether 02-04 are a fix or just hardening.) → answered by Phase 01 diagnostics.
