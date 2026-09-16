"""Database models (SQLModel). Single-admin: no users table."""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import Index, UniqueConstraint
from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_naive() -> datetime:
    # Naive UTC — SQLite returns naive datetimes, so keep scheduling naive to
    # avoid aware/naive comparison errors in the worker.
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Bot(SQLModel, table=True):
    """A registered Telegram bot (owned by the single admin)."""

    id: int | None = Field(default=None, primary_key=True)
    telegram_bot_id: int = Field(index=True, unique=True)
    username: str
    token_encrypted: bytes
    webhook_secret: str
    status: str = "active"  # active | disabled | invalid
    access_password_hash: str | None = None  # optional per-bot access lock
    created_at: datetime = Field(default_factory=_now)


class Route(SQLModel, table=True):
    """A directed forwarding rule: copy messages from source -> dest."""

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    source_chat_id: int = Field(index=True)
    dest_chat_id: int
    enabled: bool = True
    created_at: datetime = Field(default_factory=_now)


GLOBAL_SOURCE = 0  # sentinel source_chat_id: sender applies to ALL of the bot's groups


class AllowedSender(SQLModel, table=True):
    """A bot-wide allowed-sender entry. Empty (no rows for a bot) means
    'no restriction' — forward everyone. A non-empty list forwards only the
    listed usernames, across ALL of the bot's source groups.

    ``source_chat_id`` is kept for schema stability but always holds
    ``GLOBAL_SOURCE`` (0); the list is global per bot, not per group.

    ``label`` (optional) is a display name: messages from this user are
    forwarded with a '[label]' prefix.
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    source_chat_id: int = Field(default=GLOBAL_SOURCE, index=True)
    username: str  # normalized: lowercase, no leading '@'
    label: str | None = None
    created_at: datetime = Field(default_factory=_now)

    __table_args__ = (
        UniqueConstraint("bot_id", "source_chat_id", "username", name="uq_allowed_sender"),
    )


class SenderGroupAssignment(SQLModel, table=True):
    """Which global ``AllowedSender`` applies to which source group (many-to-many).

    The allowlist is declared once globally; these rows scope each sender to
    specific source groups. A source group with NO assignment rows is 'open'
    (forward everyone from it); a group with rows forwards only those senders.
    """

    id: int | None = Field(default=None, primary_key=True)
    allowed_sender_id: int = Field(foreign_key="allowedsender.id", index=True)
    source_chat_id: int = Field(index=True)
    created_at: datetime = Field(default_factory=_now)

    __table_args__ = (
        UniqueConstraint(
            "allowed_sender_id", "source_chat_id", name="uq_sender_group_assign"
        ),
        Index("ix_group_sender", "source_chat_id", "allowed_sender_id"),
    )


class ForwardJob(SQLModel, table=True):
    """Durable outbox entry: one pending delivery to a single destination chat.

    Processed strictly in id order per ``dest_chat_id`` (preserves message
    order) and retried until delivered (no message loss).
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    dest_chat_id: int = Field(index=True)
    # "copy" (copy_message) | "text" (send_message) | "copy_caption" (copy with
    # an overridden caption, used for labeled media).
    kind: str
    from_chat_id: int | None = None
    message_id: int | None = None
    text: str | None = None
    entities_json: str | None = None          # shifted entities for a labeled text job
    caption: str | None = None                # overridden caption for copy_caption
    caption_entities_json: str | None = None  # shifted caption entities
    status: str = Field(default="pending", index=True)  # pending | failed
    attempts: int = 0
    next_attempt_at: datetime = Field(default_factory=_now_naive)
    last_error: str | None = None
    created_at: datetime = Field(default_factory=_now_naive)
