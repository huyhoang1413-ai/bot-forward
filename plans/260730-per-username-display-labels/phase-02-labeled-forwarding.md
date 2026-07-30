# Phase 02 — Labeled Forwarding Mechanics

## Context links
- Parent plan: [plan.md](plan.md)
- Depends on: [Phase 01](phase-01-model-services.md) (label_map)
- Research: [researcher-01](research/researcher-01-prefix-api.md) (copy caption override, entity shift, types)
- Docs: copyMessage https://core.telegram.org/bots/api#copymessage ; MessageEntity https://core.telegram.org/bots/api#messageentity ; sendMessage https://core.telegram.org/bots/api#sendmessage

## Overview
- **Date**: 2026-07-30
- **Description**: When a message is from a labeled user, prepend `[Label]` while preserving formatting. Adds message classification, prefix + UTF-16 entity shifting, a new `copy_caption` outbox job kind, and the send handling. Unlabeled path unchanged.
- **Priority**: High (core deliverable)
- **Implementation status**: Not started
- **Review status**: Pending

## Key Insights
- Three message shapes decide the technique:
  - **text** (`msg.text`) → `send_message(text="[L] "+text, entities=shift(entities, k))`.
  - **caption-capable media** (photo/video/document/audio/animation/voice) → `copy_message(caption="[L] "+cap, caption_entities=shift(cap_entities, k))`; if no original caption → `caption="[L]"`.
  - **caption-less** (sticker/poll/dice/location/contact/venue/video_note) → emit a `text` job `"[L]"` THEN a plain `copy` job (queue keeps them adjacent + ordered).
- `k` = UTF-16 length of the prefix = `len(prefix.encode("utf-16-le"))//2` (correct for any label chars).
- Entities are shifted as raw dicts in the **pure** layer and stored as JSON on the job; botcache rebuilds `MessageEntity.de_json` at send time.
- Loop guard / commands / allowlist gate all run BEFORE labeling (unchanged). Labeling only rewrites the forward jobs.

## Requirements
- `ForwardJob` new nullable fields: `entities_json`, `caption`, `caption_entities_json`; `kind` gains `"copy_caption"`.
- Pure helpers in `forwarding.py`:
  - `classify_message(msg) -> "text" | "caption_media" | "other"` (+ detect existing caption).
  - `prefix_len16(label) -> int`.
  - `shift_entities(entities: list[dict], delta: int) -> list[dict]`.
  - `build_labeled_jobs(msg, dest, bot_id, label) -> list[ForwardJob]` per the 3 shapes.
- `build_jobs(..., label_map)`: in the forward branch, if `sender_username` has a label → use `build_labeled_jobs` per dest; else current `copy` jobs. Preserve per-dest ordering (label job before item job).
- `botcache.send_job`: handle `copy_caption` (`copy_message(caption=, caption_entities=)`) and `text` with `entities`; convert JSON dicts via `MessageEntity.de_json`.

## Architecture
```
webapp/app/
├── models.py      # ForwardJob: + entities_json, caption, caption_entities_json
├── forwarding.py  # classify_message, prefix_len16, shift_entities, build_labeled_jobs, build_jobs(label_map)
└── botcache.py    # send_job handles copy_caption + entities
```
Pseudocode (forward branch, per dest):
```python
label = label_map.get(action.sender_username) if action.sender_username else None
if not label:
    jobs.append(copy_job(dest, source, mid))
else:
    kind, cap, cap_ents = classify(msg)
    k = prefix_len16(f"[{label}] ")
    if kind == "text":
        jobs.append(text_job(dest, f"[{label}] "+msg["text"],
                             shift_entities(msg.get("entities",[]), k)))
    elif kind == "caption_media":
        cap0 = msg.get("caption")
        cap = f"[{label}] "+cap0 if cap0 else f"[{label}]"
        ents = shift_entities(msg.get("caption_entities",[]), k) if cap0 else []
        jobs.append(copy_caption_job(dest, source, mid, cap, ents))
    else:  # other -> label line then copy
        jobs.append(text_job(dest, f"[{label}]", []))
        jobs.append(copy_job(dest, source, mid))
```

## Related code files
- `webapp/app/models.py`, `forwarding.py`, `botcache.py` (edit)
- Tests: `webapp/tests/test_forwarding.py`, `test_worker.py` (extend)

## Implementation Steps
1. Extend `ForwardJob` (nullable entities/caption fields).
2. Implement `classify_message`, `prefix_len16`, `shift_entities` (pure) + tests.
3. Implement `build_labeled_jobs` + wire into `build_jobs(label_map)`; keep unlabeled path identical.
4. Update `botcache.send_job` for `copy_caption` + `text` entities (`MessageEntity.de_json`).
5. Tests (no mocks): entity shift correctness (UTF-16), text/caption/other job shapes, unlabeled unchanged, ordering (label before item) via the worker.

## Todo list
- [ ] ForwardJob new fields
- [ ] classify_message / prefix_len16 / shift_entities (+tests)
- [ ] build_labeled_jobs + build_jobs(label_map)
- [ ] botcache send_job copy_caption + entities
- [ ] worker/ordering test: "[L]" arrives before caption-less item

## Success Criteria
- Text from a labeled user arrives as `[L] text` with **original bold/link/emoji intact**.
- Photo with caption → `[L] caption` (formatting intact); photo without caption → caption `[L]`.
- Sticker/poll → a `[L]` message immediately precedes the item, in order.
- Unlabeled users forward exactly as before (plain copy).
- Entities never mis-align (offsets shifted by correct UTF-16 amount).

## Risk Assessment
- **Medium**: entity offset math (UTF-16) — cover with tests incl. a multi-byte char in the body. Wrong shift → broken formatting.
- **Medium**: doubling messages for caption-less types — acceptable per decision; document.
- **Low**: `copy_caption` caption length limit (1024) — truncate prefix+caption if needed; note.

## Security Considerations
- Label already validated (no `[`/`]`/newline/control chars) so it can't inject fake entities or break rendering.
- Never pass `parse_mode` with `entities` (Telegram rejects) — always entities-only.

## Next steps
Proceed to [Phase 03](phase-03-ui-docs.md) — UI to manage labels + docs.
