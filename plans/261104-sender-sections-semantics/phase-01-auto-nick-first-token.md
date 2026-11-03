# Phase 01 — Auto-nick = first token before the first space

## Context links
- Parent: [plan.md](./plan.md) · Depends on: none · Research: [research/researcher-01-first-name.md](./research/researcher-01-first-name.md) · Audit: [reports/01-conformance-audit.md](./reports/01-conformance-audit.md)

## Overview
- Date: 2026-11-04
- Description: Make "Nickname tự động" use only the first whitespace-delimited token of `first_name` ("Minh Anh" → "Minh"), per your spec. **D1 RESOLVED → first-token.** Capture-once semantics unchanged.
- Priority: High · Implementation status: Not started · Review status: Pending

## Key Insights
- `first_name` can contain spaces/emoji/multi-word (researcher-01). First token = text before first space.
- Auto-nick value is produced in ONE place: `resolve_label` returns `prof.label_override or prof.first_name` ([services.py:639](../../webapp/app/services.py#L639)). Applying the trim at RESOLVE time (not capture) keeps the full name stored (editable) while only the auto-derived display is trimmed — safest + reversible.
- Manual label (section 1) and `label_override` must NOT be trimmed — only the auto first_name path.

## Requirements
- When auto-nick is on and no manual/override label exists: nickname = `first_token(first_name)`.
- Fallback: if first token is empty (pure whitespace/emoji) → use the full stripped `first_name`; if that's empty → no label.
- Manual label + `label_override` returned verbatim (untrimmed).

## Architecture
New pure helper in `forwarding.py` (pure, testable):
```python
def first_token(name: str | None) -> str | None:
    """First whitespace-delimited token of a name (Telegram first_name may be
    multi-word). Falls back to the full stripped name, then None."""
    if not name:
        return None
    parts = name.split()           # splits on any unicode whitespace run
    return (parts[0] if parts else name.strip()) or None
```
Apply ONLY on the auto path in `resolve_label` ([services.py:627-639](../../webapp/app/services.py#L627-L639)):
```python
if manual_label:
    return manual_label            # verbatim
...
return prof.label_override or first_token(prof.first_name)   # trim only auto first_name
```
(Import `first_token` from app.forwarding.)

## Related code files
- `webapp/app/forwarding.py` (add `first_token`), `webapp/app/services.py` (`resolve_label` auto path).

## Implementation Steps
1. Add `first_token` helper. 2. Use it in `resolve_label` auto branch only. 3. Leave `capture_sender` storing full `first_name` (so edits keep context). 4. Tests (Phase 04).

## Todo list
- [ ] `first_token` helper (handles None/whitespace/emoji)
- [ ] applied only to auto first_name, not manual/override labels
- [ ] "Minh Anh" → "Minh"; "" / emoji-only → sensible fallback

## Success Criteria
- Auto-nick shows the first token; manual nicknames unaffected.

## Risk Assessment
- Low + reversible (trim at resolve, full name retained). Only active when `auto_nick` on.
- D1 risk: Vietnamese 2-syllable given names lose the 2nd syllable — this is your stated spec; confirm in review.

## Security Considerations
- `sanitize_label` still runs downstream (strips [],newlines, clamps 32) — unchanged.

## Next steps
Phase 02: wording.
