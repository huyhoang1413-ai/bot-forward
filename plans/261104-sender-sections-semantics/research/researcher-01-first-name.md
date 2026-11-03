# Telegram Bot API: User.first_name Research

## Q1: What exactly is `User.first_name`?

- **Required field.** No "_Optional_" designation in [core.telegram.org/bots/api#user](https://core.telegram.org/bots/api#user).
- **Definition:** "User's or bot's first name" (string type).
- **Spaces/multiword:** API docs do NOT prohibit spaces or compound names. Practical assumption: users often put entire display name (e.g., "John Smith" or "محمد علي") in first_name, not just given name.
- **last_name:** Separate, explicitly _Optional_ field for last name. Bot cannot assume two-part name split.

## Q2: Is `first_name` always present for real users?

- **Yes (for real users).** Required field in User object definition.
- **Bots:** Bot accounts also have first_name (required). No "anonymous user" case in standard Bot API.
- **Edge case:** Service messages (no User object) don't carry first_name; only Message.from_user objects do.

## Q3: Auto-nickname extraction: is `first_name.split()[0]` reasonable? Unicode/space edge cases?

- **Approach OK.** Whitespace-delimited split to grab first word is standard & works for most locales (Latin, Cyrillic, Arabic, CJK).
- **Edge cases to handle:**
  - **Zero-break space (U+200B), no-break space (U+00A0), tabs:** `split()` (no args) handles all Unicode whitespace ✓
  - **Emoji-only first_name:** e.g., "🎨". `split()[0]` → "🎨" (valid nickname, no fallback needed).
  - **Pure spaces/whitespace:** e.g., "   ". `split()` → `[]` → `IndexError`. **Fallback needed:** use fallback_id or user_id.
  - **RTL text (Arabic, Hebrew):** Split by first space works correctly; no special handling needed.
  - **CJK (no spaces):** e.g., "张伟". `split()[0]` → "张伟" (entire name). Acceptable; CJK typically no word breaks.

## Q4: Does `first_name` change if user renames? Capture-once vs refresh?

- **Update objects are snapshots.** Each incoming Update contains User data as it existed when update was generated.
- **Implication:** If user changes first_name at timestamp T, updates received before T have old name; updates after T have new name.
- **Recommendation:** **Capture-once strategy** for auto-nickname (on first message from sender). Reasoning:
  - Refreshing nickname on every message wastes resources & creates UI flicker.
  - User expectation: once assigned nickname = stays consistent in thread, even if user later renames.
  - Trade-off: nickname may become stale, but coherent conversation context.
- **Alternative:** Store (user_id, first_name, timestamp) mapping; refresh only if >7 days old or explicit user action.

## Core Findings

| Question | Answer | Source |
|----------|--------|--------|
| **Type** | Required string field | [core.telegram.org/bots/api#user](https://core.telegram.org/bots/api#user) |
| **Content** | User's name (may span multiple words, emoji, mixed scripts) | Telegram API spec |
| **Always present?** | Yes (required for real users & bots) | API definition |
| **Split logic safe?** | Yes; use `.split()[0]` with fallback for whitespace-only | Handles Unicode whitespace ✓ |
| **Update semantics** | Snapshot, not retroactive refresh | Update object behavior |
| **Strategy** | Capture-once (first message) | Balances coherence vs. staleness |

## Implementation Notes

```python
def extract_nickname(first_name: str, user_id: int) -> str:
    """Extract short nickname from first_name. Fallback to user_id."""
    if not first_name or not first_name.strip():
        return f"User{user_id}"
    
    tokens = first_name.split()  # Handles all Unicode whitespace
    return tokens[0] if tokens else f"User{user_id}"
```

## Unresolved Questions

- **Exact max length of first_name:** Telegram client UI constraint is ~64 chars, but API does not document limit. Recommend truncate at 100 chars for safety.
- **Locale-specific best practices:** No Telegram docs on recommended nickname extraction for specific languages (e.g., Thai, Hindi word boundaries). Test per-locale if supporting non-Latin scripts at scale.
