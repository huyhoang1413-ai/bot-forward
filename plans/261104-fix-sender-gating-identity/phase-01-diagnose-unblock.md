# Phase 01 — Diagnose + immediate unblock (no deploy)

## Context links
- Parent: [plan.md](./plan.md) · Depends on: none · Analysis: [reports/01-root-cause-analysis.md](./reports/01-root-cause-analysis.md)

## Overview
- Date: 2026-11-04
- Description: Query the live DB (VPS 26) to confirm WHY only Antony forwards, decide the intent for the 2 routes, and — if intent is "forward everyone" — open the groups by deleting their per-group assignments. Restores forwarding immediately with no code change/deploy.
- Priority: **Critical** · Implementation status: Not started · Review status: Pending

## Key Insights
- A source group with per-group assignments is RESTRICTED to those usernames; a group with NO assignments is OPEN (forward everyone) — [forwarding.py:338-344](../../webapp/app/forwarding.py#L338-L344).
- So "only Antony" ⇒ those groups HAVE assignments AND only Antony's live @username matches. Deleting the assignments re-opens the groups instantly.
- `_backfill_group_sender_assignments()` ([db.py:124](../../webapp/app/db.py#L124)) auto-assigns every global sender to every source group on startup — a likely source of unintended gating. Deleting rows is safe; it only re-runs for senders that still exist.

## Requirements
- Identify bot id of @WeFunForward_bot and its 2 routes' source_chat_ids.
- Report: allowlist size, assignment count per source group, how many assigned senders actually have a username recorded.
- Decide: everyone vs specific people.

## Architecture / diagnostic commands (run on VPS 26, `~/bot-forward/webapp`)
```bash
# 1) bot id + its routes
docker compose exec -T web python - <<'PY'
import sqlite3; d=sqlite3.connect('/app/data/app.db')
b=d.execute("select id,username from bot where username like 'WeFunForward%'").fetchone(); print("bot",b)
bid=b[0]
print("routes:");
for r in d.execute("select id,source_chat_id,dest_chat_id,enabled from route where bot_id=?",(bid,)): print(" ",r)
print("allowlist size:", d.execute("select count(*) from allowedsender where bot_id=?",(bid,)).fetchone()[0])
print("assignments per source group:")
for r in d.execute("""select sga.source_chat_id, count(*) from sendergroupassignment sga
  join allowedsender a on a.id=sga.allowed_sender_id where a.bot_id=? group by 1""",(bid,)): print(" ",r)
PY
```
### If intent = forward EVERYONE on a source group → open it (delete its assignments):
```bash
docker compose exec -T web python - <<'PY'
import sqlite3; d=sqlite3.connect('/app/data/app.db')
SRC = -1003926744177   # <-- set each source_chat_id you want fully open
bid = d.execute("select id from bot where username like 'WeFunForward%'").fetchone()[0]
n = d.execute("""delete from sendergroupassignment where source_chat_id=? and allowed_sender_id in
  (select id from allowedsender where bot_id=?)""",(SRC,bid)).rowcount
d.commit(); print("deleted",n,"assignments -> group",SRC,"now OPEN (forward everyone)")
PY
```
(No restart needed — webhook reads assignments per request. Send a test message from a no-username member → should forward.)

## Related code files
- Read-only: [forwarding.py](../../webapp/app/forwarding.py), [db.py:124](../../webapp/app/db.py#L124). No code edits in this phase.

## Implementation Steps
1. Run diagnostic block → capture output. 2. Confirm intent per route with the user. 3. For "everyone" groups, run the delete block per source_chat_id. 4. Send a test message from a member WITHOUT a username; confirm it forwards. 5. Record decision in plan.md "Decision gate".

## Todo list
- [ ] Diagnostics captured (routes, allowlist size, assignments/group)
- [ ] Intent decided per route (everyone vs specific)
- [ ] (if everyone) assignments deleted for those groups
- [ ] Test message from a no-username member forwards

## Success Criteria
- Messages from members other than Antony forward again on the affected routes.

## Risk Assessment
- Low. Deleting assignments only widens who is forwarded; it never blocks. Reversible (re-add via UI). If intent is "specific people", DO NOT delete — go to Phase 02-04 instead.

## Security Considerations
- Widening a group to "everyone" forwards all members' messages — confirm that is acceptable for each route before deleting.

## Next steps
If intent is "specific people" (or to prevent recurrence regardless): Phase 02.
