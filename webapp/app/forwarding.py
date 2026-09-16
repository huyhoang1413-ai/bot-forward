"""Shared forwarding logic used by every bot's webhook.

The decision layer (``decide_action`` / ``select_destinations``) is pure so it
can be unit-tested without any Telegram network calls or mocks.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass

from app.models import ForwardJob, Route

logger = logging.getLogger(__name__)

# Telegram username: 5-32 chars, letters/digits/underscore (case-insensitive).
USERNAME_RE = re.compile(r"^[a-z0-9_]{5,32}$")

# Media types that carry a caption (so a label can be prepended to it).
CAPTION_MEDIA_KEYS = ("photo", "video", "document", "audio", "animation", "voice")

# Telegram content limits; over these we forward unlabeled instead of dropping.
TEXT_LIMIT = 4096
CAPTION_LIMIT = 1024


def normalize_username(username: str) -> str:
    """Lowercase and strip a leading '@' for consistent storage/matching."""
    return username.strip().lstrip("@").lower()


def is_valid_username(username: str) -> bool:
    return bool(USERNAME_RE.fullmatch(normalize_username(username)))


def is_valid_label(label: str) -> bool:
    """Display label: 1-32 printable chars, no brackets or line breaks."""
    label = label.strip()
    if not (1 <= len(label) <= 32):
        return False
    if any(ch in label for ch in "[]\r\n"):
        return False
    return label.isprintable()


def prefix_len16(prefix: str) -> int:
    """Length of a string in UTF-16 code units (Telegram entity offset unit)."""
    return len(prefix.encode("utf-16-le")) // 2


def shift_entities(entities, delta: int) -> list[dict]:
    """Return entity dicts with every offset shifted by ``delta`` (for a prefix)."""
    out: list[dict] = []
    for e in entities or []:
        e2 = dict(e)
        e2["offset"] = int(e.get("offset", 0)) + delta
        out.append(e2)
    return out


def classify_message(msg: dict) -> str:
    """text | caption_media | other (sticker/poll/location/... — no caption)."""
    if msg.get("text") is not None:
        return "text"
    if any(k in msg for k in CAPTION_MEDIA_KEYS):
        return "caption_media"
    return "other"


def _copy_job(bot_id: int, dest: int, source: int, message_id) -> ForwardJob:
    return ForwardJob(
        bot_id=bot_id, dest_chat_id=dest, kind="copy",
        from_chat_id=source, message_id=message_id,
    )


def _text_job(bot_id: int, dest: int, text: str, entities: list[dict]) -> ForwardJob:
    return ForwardJob(
        bot_id=bot_id, dest_chat_id=dest, kind="text", text=text,
        entities_json=json.dumps(entities) if entities else None,
    )


def _copy_caption_job(
    bot_id: int, dest: int, source: int, message_id, caption: str, entities: list[dict]
) -> ForwardJob:
    return ForwardJob(
        bot_id=bot_id, dest_chat_id=dest, kind="copy_caption",
        from_chat_id=source, message_id=message_id, caption=caption,
        caption_entities_json=json.dumps(entities) if entities else None,
    )


def build_labeled_jobs(
    msg: dict, dest: int, bot_id: int, source: int, message_id, label: str
) -> list[ForwardJob]:
    """Jobs that deliver one message to ``dest`` with a '[label]' prefix.

    Preserves formatting by shifting entity offsets. Falls back to a plain copy
    (unlabeled) if the prefixed text/caption would exceed Telegram's limits,
    rather than dropping the message.
    """
    prefix = f"[{label}] "
    k = prefix_len16(prefix)
    shape = classify_message(msg)

    if shape == "text":
        new_text = prefix + (msg.get("text") or "")
        if prefix_len16(new_text) > TEXT_LIMIT:  # Telegram limits are UTF-16 units
            return [_copy_job(bot_id, dest, source, message_id)]
        return [_text_job(bot_id, dest, new_text, shift_entities(msg.get("entities"), k))]

    if shape == "caption_media":
        cap0 = msg.get("caption")
        if cap0:
            new_cap = prefix + cap0
            if prefix_len16(new_cap) > CAPTION_LIMIT:  # UTF-16 units
                return [_copy_job(bot_id, dest, source, message_id)]
            ents = shift_entities(msg.get("caption_entities"), k)
        else:
            new_cap = f"[{label}]"
            ents = []
        return [_copy_caption_job(bot_id, dest, source, message_id, new_cap, ents)]

    # other (no text/caption) -> a "[label]" line, then the item copied as-is
    return [
        _text_job(bot_id, dest, f"[{label}]", []),
        _copy_job(bot_id, dest, source, message_id),
    ]


@dataclass
class Action:
    kind: str  # "skip" | "chatid" | "start" | "forward"
    source_chat_id: int | None = None
    message_id: int | None = None
    sender_username: str | None = None  # normalized sender username (forward only)


def decide_action(update: dict, telegram_bot_id: int) -> Action:
    """Decide what to do with a raw Telegram update dict.

    Order matters: the loop guard (ignore the bot's own messages) runs BEFORE
    command handling so copied messages that happen to start with "/chatid"
    do not trigger a reply or a re-forward.
    """
    msg = update.get("message") or update.get("edited_message")
    if not isinstance(msg, dict):
        return Action("skip")

    chat = msg.get("chat") or {}
    source = chat.get("id")
    if source is None:
        return Action("skip")

    from_user = msg.get("from") or {}
    if from_user.get("id") == telegram_bot_id:
        return Action("skip")  # loop guard

    text = msg.get("text") or ""
    if text.startswith("/chatid"):
        return Action("chatid", source_chat_id=source)
    if text.startswith("/start"):
        return Action("start", source_chat_id=source)

    raw_username = from_user.get("username")
    sender_username = normalize_username(raw_username) if raw_username else None
    return Action(
        "forward",
        source_chat_id=source,
        message_id=msg.get("message_id"),
        sender_username=sender_username,
    )


def is_sender_allowed(sender_username: str | None, allowed: set[str]) -> bool:
    """Whitelist check. Empty allowlist -> no restriction (forward everyone).

    A non-empty list forwards only listed usernames; a message with no username
    (None) is blocked (anonymous admins, channel posts, users without a username).
    """
    if not allowed:
        return True
    return sender_username is not None and sender_username in allowed


def select_destinations(routes: Sequence[Route], source_chat_id: int) -> list[int]:
    """Enabled destination chat ids for a given source (pure)."""
    return [
        r.dest_chat_id
        for r in routes
        if r.enabled and r.source_chat_id == source_chat_id
    ]


_START_TEXT = (
    "Forward bot is active. Add me as admin to your groups, send /chatid in each "
    "group to get its id, then configure a route in the web panel."
)


def build_jobs(
    update: dict,
    telegram_bot_id: int,
    routes: Sequence[Route],
    bot_id: int,
    allowed_senders: dict[str, str | None] | None = None,
) -> list[ForwardJob]:
    """Turn one update into durable outbox jobs (pure — inserts happen later).

    Jobs are created per destination in a deterministic order, so their row ids
    preserve the source message order for each destination chat.

    ``allowed_senders`` is the bot's global allowlist: {username: label_or_None}.
    A non-empty map forwards only those usernames (from any group); an empty /
    missing map forwards everyone. A username's label (if set) prefixes its
    forwarded messages with '[label]'. Commands (/chatid, /start) are never gated.
    """
    action = decide_action(update, telegram_bot_id)

    if action.kind == "skip":
        return []
    if action.kind == "chatid":
        return [
            ForwardJob(
                bot_id=bot_id,
                dest_chat_id=action.source_chat_id,
                kind="text",
                text=f"chat_id: {action.source_chat_id}",
            )
        ]
    if action.kind == "start":
        return [
            ForwardJob(
                bot_id=bot_id,
                dest_chat_id=action.source_chat_id,
                kind="text",
                text=_START_TEXT,
            )
        ]

    # forward -> gate by the bot's global allowlist, then one job per dest
    allowed = allowed_senders or {}
    if not is_sender_allowed(action.sender_username, set(allowed.keys())):
        return []

    label = allowed.get(action.sender_username) if action.sender_username else None
    msg = update.get("message") or update.get("edited_message") or {}

    jobs: list[ForwardJob] = []
    for dest in select_destinations(routes, action.source_chat_id):
        if label:
            jobs.extend(
                build_labeled_jobs(
                    msg, dest, bot_id, action.source_chat_id, action.message_id, label
                )
            )
        else:
            jobs.append(_copy_job(bot_id, dest, action.source_chat_id, action.message_id))
    return jobs
