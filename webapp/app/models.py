"""Database models (SQLModel). Multi-tenant: teams own bots; users belong to a team."""

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


class Team(SQLModel, table=True):
    """A tenant. Bots belong to a team; team members share visibility."""

    id: int | None = Field(default=None, primary_key=True)
    name: str = Field(index=True, unique=True)
    created_at: datetime = Field(default_factory=_now)


class User(SQLModel, table=True):
    """A panel user in exactly one team. The super-admin is NOT a row here
    (it authenticates from .env); this table holds team members only."""

    id: int | None = Field(default=None, primary_key=True)
    username: str = Field(index=True, unique=True)  # normalized lowercase
    password_hash: str
    team_id: int | None = Field(default=None, foreign_key="team.id", index=True)
    created_at: datetime = Field(default_factory=_now)


class Bot(SQLModel, table=True):
    """A registered Telegram bot, owned by a team (team_id NULL = admin-only)."""

    id: int | None = Field(default=None, primary_key=True)
    telegram_bot_id: int = Field(index=True, unique=True)
    username: str
    token_encrypted: bytes
    webhook_secret: str
    status: str = "active"  # active | disabled | invalid
    access_password_hash: str | None = None  # optional per-bot access lock
    team_id: int | None = Field(default=None, foreign_key="team.id", index=True)
    auto_nick: bool = Field(default=False)  # auto-prefix forwards with sender first_name
    created_at: datetime = Field(default_factory=_now)


class Route(SQLModel, table=True):
    """A directed forwarding rule: copy messages from source -> dest.

    Optional forum topic scoping: ``source_thread_id``/``dest_thread_id`` are a
    message_thread_id (None = whole group / General). A source route with
    source_thread_id=None matches every topic of the group.
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(foreign_key="bot.id", index=True)
    source_chat_id: int = Field(index=True)
    source_thread_id: int | None = Field(default=None, index=True)
    dest_chat_id: int
    dest_thread_id: int | None = Field(default=None)
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


class SenderProfile(SQLModel, table=True):
    """Captured sender identity for auto-nickname.

    ``first_name`` is captured ONCE (first message seen) and never overwritten;
    ``label_override`` is an admin edit that wins over it. Keyed by user_id so it
    covers senders without a username.
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    telegram_user_id: int = Field(index=True)
    first_name: str
    label_override: str | None = None
    username: str | None = None
    captured_at: datetime = Field(default_factory=_now)

    __table_args__ = (
        UniqueConstraint("bot_id", "telegram_user_id", name="uq_sender_profile"),
        Index("ix_sender_profile_bot_first", "bot_id", "first_name"),
    )


class ForwardJob(SQLModel, table=True):
    """Durable outbox entry: one pending delivery to a single destination chat.

    Processed strictly in id order per ``dest_chat_id`` (preserves message
    order) and retried until delivered (no message loss).
    """

    id: int | None = Field(default=None, primary_key=True)
    bot_id: int = Field(index=True)
    dest_chat_id: int = Field(index=True)
    dest_thread_id: int | None = None  # target forum topic (None = General/normal)
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
