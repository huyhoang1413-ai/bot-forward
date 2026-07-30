# Plan: Per-Username Display Labels ([Name] prefix on forwards)

## Goal
Attach a display name to a username so forwarded messages are prefixed, e.g. `@fbagency999` → label `Doby` → the destination shows `[Doby] <original message>`. Builds on the existing `webapp/` forwarder + allowlist.

## Decisions (confirmed with user)
- **Storage**: a **separate** per-bot `username → label` map (independent of the allowlist). Works even in "forward everyone" mode (label specific people without restricting).
- **Preserve formatting**: keep the original bold/links/emoji — prepend the label and **shift message entity offsets** (UTF-16 units).
- **No-text messages** (sticker, poll, location…): can't embed text → send a small `[Doby]` **text message right before** the copied item (our ordered outbox keeps them adjacent).
- Prefix format: `[Label] ` before content; standalone `[Label]` when there is no original text.
- No label for a username → forward exactly as today.

## Key technical facts (from research)
- `copy_message` copies verbatim and **cannot prepend to a text body**. For text we must `send_message(text=prefix+text, entities=shifted)`. [researcher-01](research/researcher-01-prefix-api.md)
- `copy_message` **can override the caption** of caption-capable media via `caption` + `caption_entities` → use it to prepend on photo/video/document/audio/animation/voice.
- Entity offsets are **UTF-16 code units** → shift = UTF-16 length of the prefix (`len(prefix.encode('utf-16-le'))//2`) — robust for any label chars.
- PTB v21: build entities via `MessageEntity.de_json(dict, bot)`; cannot pass `parse_mode` together with `entities`.
- Caption-less types (sticker/poll/dice/location/contact/venue/video_note) → separate `[Label]` message then copy. [researcher-02](research/researcher-02-label-design.md)

## Scope
**In**: `SenderLabel(bot_id, username, label)` table + services CRUD; webhook loads label map; message classification + prefix + entity-shift; new outbox job kind `copy_caption` (+ entities on `text` jobs); botcache send handling; UI to set labels per username; tests; docs.
**Out (v2)**: per-source-group label override, suffix/footer templates, HTML template placeholders, label by user-id, retroactive relabel of already-sent messages.

## Relationship to existing code
Extends `webapp/`. Reuses the durable outbox + ordering (label + item stay adjacent). Unlabeled path unchanged (still plain `copy_message`). Allowlist unaffected (orthogonal feature).

## Phases
| # | Phase | Status | Progress | File |
|---|-------|--------|----------|------|
| 01 | Data model + services + webhook wiring | Not started | 0% | [phase-01](phase-01-model-services.md) |
| 02 | Labeled forwarding mechanics + tests | Not started | 0% | [phase-02](phase-02-labeled-forwarding.md) |
| 03 | Admin UI + docs | Not started | 0% | [phase-03](phase-03-ui-docs.md) |

## Research
- [researcher-01 — prefix/caption API mechanics](research/researcher-01-prefix-api.md)
- [researcher-02 — label data model & UX](research/researcher-02-label-design.md)

## Tech stack
Unchanged: FastAPI, SQLModel, SQLite, python-telegram-bot v21, Jinja2.

## Open questions
1. Label scope per-bot (planned) vs per-source-group — per-bot chosen (a person's name is the same in all groups; covers both bridge sides automatically). Confirm.
2. Doubling for caption-less types (extra `[Label]` message) acceptable vs skipping label on those? (plan: send the extra message per user's choice).
3. Max label length / allowed chars (plan: ≤32, printable, no `[` `]` newline). Confirm.
