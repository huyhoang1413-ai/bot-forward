"""Bot lifecycle & route operations (DB + Telegram side effects)."""

from __future__ import annotations

import logging
import secrets

from sqlalchemy import func
from sqlmodel import Session, select

from app import botcache, telegram_api
from app.crypto import decrypt_token, encrypt_token
from app.forwarding import normalize_username
from app.models import (
    GLOBAL_SOURCE,
    AllowedSender,
    Bot,
    ForwardJob,
    Route,
    SenderGroupAssignment,
    Team,
    User,
)
from app.pw import hash_password

logger = logging.getLogger(__name__)


class DuplicateBotError(Exception):
    """Raised when the same Telegram bot is added twice."""


async def add_bot(
    session: Session,
    token: str,
    access_password: str | None = None,
    team_id: int | None = None,
) -> Bot:
    """Validate a token, store it encrypted, and register its webhook.

    ``access_password`` (optional) locks the bot's page behind that password.
    ``team_id`` (optional) sets the owning team (None = admin-only).
    Raises telegram_api.InvalidTokenError or DuplicateBotError.
    """
    token = token.strip()
    telegram_bot_id, username = await telegram_api.validate_token(token)

    existing = session.exec(
        select(Bot).where(Bot.telegram_bot_id == telegram_bot_id)
    ).first()
    if existing:
        raise DuplicateBotError(f"Bot @{existing.username} is already registered.")

    access_password = (access_password or "").strip()
    bot = Bot(
        telegram_bot_id=telegram_bot_id,
        username=username,
        token_encrypted=encrypt_token(token),
        webhook_secret=secrets.token_urlsafe(32),
        status="active",
        access_password_hash=hash_password(access_password) if access_password else None,
        team_id=team_id,
    )
    session.add(bot)
    session.commit()
    session.refresh(bot)

    # Webhook URL needs the DB id, so register after insert.
    try:
        await telegram_api.register_webhook(bot.id, token, bot.webhook_secret)
    except Exception as exc:
        bot.status = "invalid"
        session.add(bot)
        session.commit()
        logger.error("setWebhook failed for bot %s: %s", bot.id, exc)
        raise
    return bot


async def remove_bot(session: Session, bot_id: int) -> None:
    """Delete a bot and its routes, and clear its webhook."""
    bot = session.get(Bot, bot_id)
    if not bot:
        return
    try:
        await telegram_api.unregister_webhook(decrypt_token(bot.token_encrypted))
    except Exception as exc:  # best-effort; still delete locally
        logger.warning("deleteWebhook failed for bot %s: %s", bot_id, exc)

    for route in session.exec(select(Route).where(Route.bot_id == bot_id)).all():
        session.delete(route)
    for job in session.exec(select(ForwardJob).where(ForwardJob.bot_id == bot_id)).all():
        session.delete(job)
    allowed_rows = session.exec(
        select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    ).all()
    allowed_ids = [a.id for a in allowed_rows]
    if allowed_ids:
        for assign in session.exec(
            select(SenderGroupAssignment).where(
                SenderGroupAssignment.allowed_sender_id.in_(allowed_ids)
            )
        ).all():
            session.delete(assign)
    for allowed in allowed_rows:
        session.delete(allowed)
    session.delete(bot)
    session.commit()
    await botcache.evict(bot_id)


async def resync_all_webhooks(session: Session) -> None:
    """Re-register webhooks for all active bots (called on startup)."""
    bots = session.exec(select(Bot).where(Bot.status == "active")).all()
    for bot in bots:
        try:
            await telegram_api.register_webhook(
                bot.id, decrypt_token(bot.token_encrypted), bot.webhook_secret
            )
        except Exception as exc:
            bot.status = "invalid"
            session.add(bot)
            session.commit()
            logger.error("resync setWebhook failed for bot %s: %s", bot.id, exc)


def add_route(
    session: Session,
    bot_id: int,
    source_chat_id: int,
    dest_chat_id: int,
    bidirectional: bool = False,
    source_thread_id: int | None = None,
    dest_thread_id: int | None = None,
) -> list[Route]:
    """Create one directed route (or two, if bidirectional).

    Optional forum topic scoping; the reverse route swaps BOTH chat and topic.
    """
    created: list[Route] = []
    # (source_chat, source_thread, dest_chat, dest_thread)
    pairs = [(source_chat_id, source_thread_id, dest_chat_id, dest_thread_id)]
    if bidirectional:
        pairs.append((dest_chat_id, dest_thread_id, source_chat_id, source_thread_id))

    for src, sthr, dst, dthr in pairs:
        exists = session.exec(
            select(Route).where(
                Route.bot_id == bot_id,
                Route.source_chat_id == src,
                Route.source_thread_id == sthr,
                Route.dest_chat_id == dst,
                Route.dest_thread_id == dthr,
            )
        ).first()
        if exists:
            continue
        route = Route(
            bot_id=bot_id, source_chat_id=src, source_thread_id=sthr,
            dest_chat_id=dst, dest_thread_id=dthr,
        )
        session.add(route)
        created.append(route)
    session.commit()
    return created


def update_route(
    session: Session,
    route_id: int,
    bot_id: int,
    source_chat_id: int,
    dest_chat_id: int,
    source_thread_id: int | None = None,
    dest_thread_id: int | None = None,
) -> bool:
    """Edit an existing route in place (bot-scoped). Returns False on IDOR miss."""
    route = session.get(Route, route_id)
    if not route or route.bot_id != bot_id:
        return False
    route.source_chat_id = source_chat_id
    route.dest_chat_id = dest_chat_id
    route.source_thread_id = source_thread_id
    route.dest_thread_id = dest_thread_id
    session.add(route)
    session.commit()
    return True


def delete_route(session: Session, route_id: int, bot_id: int | None = None) -> None:
    route = session.get(Route, route_id)
    # Scope the delete to the bot in the URL to avoid cross-bot deletion (IDOR).
    if not route or (bot_id is not None and route.bot_id != bot_id):
        return
    owner_bot_id = route.bot_id
    source = route.source_chat_id
    session.delete(route)
    session.commit()

    # Best-effort: if that source group has no routes left, drop its stale
    # per-group assignments (they would never match again anyway).
    remaining = session.exec(
        select(Route).where(
            Route.bot_id == owner_bot_id, Route.source_chat_id == source
        )
    ).first()
    if remaining is not None:
        return
    own_ids = [
        s.id
        for s in session.exec(
            select(AllowedSender).where(AllowedSender.bot_id == owner_bot_id)
        ).all()
    ]
    if not own_ids:
        return
    stale = session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.source_chat_id == source,
            SenderGroupAssignment.allowed_sender_id.in_(own_ids),
        )
    ).all()
    for a in stale:
        session.delete(a)
    if stale:
        session.commit()


def add_allowed_sender(
    session: Session,
    bot_id: int,
    username: str,
    label: str | None = None,
) -> AllowedSender:
    """Add a username to the bot's global allowlist (normalized, deduped).

    The list is bot-wide: a listed username is forwarded from ALL of the bot's
    groups. ``label`` (optional) sets the display name; on an existing row it
    updates it.
    """
    username = normalize_username(username)
    label = (label or "").strip() or None

    exists = session.exec(
        select(AllowedSender).where(
            AllowedSender.bot_id == bot_id,
            AllowedSender.source_chat_id == GLOBAL_SOURCE,
            AllowedSender.username == username,
        )
    ).first()
    if exists:
        if label is not None:
            exists.label = label
            session.add(exists)
        session.commit()
        return exists

    row = AllowedSender(
        bot_id=bot_id, source_chat_id=GLOBAL_SOURCE, username=username, label=label
    )
    session.add(row)
    session.commit()
    session.refresh(row)
    return row


def set_bot_password(session: Session, bot_id: int, password: str) -> None:
    """Set/clear a bot's access password (blank password clears the lock)."""
    bot = session.get(Bot, bot_id)
    if not bot:
        return
    password = (password or "").strip()
    bot.access_password_hash = hash_password(password) if password else None
    session.add(bot)
    session.commit()


def update_allowed_label(
    session: Session, allowed_id: int, label: str, bot_id: int | None = None
) -> None:
    """Set/clear the display label on an existing allowlist row (scoped to bot)."""
    row = session.get(AllowedSender, allowed_id)
    if row and (bot_id is None or row.bot_id == bot_id):
        row.label = label.strip() or None
        session.add(row)
        session.commit()


def delete_allowed_sender(
    session: Session, allowed_id: int, bot_id: int | None = None
) -> None:
    row = session.get(AllowedSender, allowed_id)
    if row and (bot_id is None or row.bot_id == bot_id):
        # Cascade: drop this sender's per-group assignments first.
        for a in session.exec(
            select(SenderGroupAssignment).where(
                SenderGroupAssignment.allowed_sender_id == allowed_id
            )
        ).all():
            session.delete(a)
        session.delete(row)
        session.commit()


# --- Sender search / pagination (scales to 500-1000 senders) ---

PAGE_SIZE = 50


def _norm_q(q: str | None) -> str:
    """Normalize a search term the same way usernames are stored (lowercase, no '@')."""
    return (q or "").strip().lstrip("@").lower()


def _paginate(session: Session, base, page: int, page_size: int):
    """Return (items, total) for a select, ordered by username, offset-paginated."""
    total = session.exec(select(func.count()).select_from(base.subquery())).one()
    page = max(0, page)
    items = session.exec(
        base.order_by(AllowedSender.username).offset(page * page_size).limit(page_size)
    ).all()
    return items, total


def list_senders(
    session: Session, bot_id: int, q: str = "", page: int = 0, page_size: int = PAGE_SIZE
):
    """The bot's registry senders, prefix-searched by username, paginated."""
    base = select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    if q:
        base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    return _paginate(session, base, page, page_size)


def list_group_senders(
    session: Session, bot_id: int, source_chat_id: int, q: str = "",
    page: int = 0, page_size: int = PAGE_SIZE,
):
    """Senders assigned to one source group (JOIN), prefix-searched, paginated."""
    base = (
        select(AllowedSender)
        .join(
            SenderGroupAssignment,
            AllowedSender.id == SenderGroupAssignment.allowed_sender_id,
        )
        .where(
            AllowedSender.bot_id == bot_id,
            SenderGroupAssignment.source_chat_id == source_chat_id,
        )
    )
    if q:
        base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    return _paginate(session, base, page, page_size)


def search_unassigned(
    session: Session, bot_id: int, source_chat_id: int, q: str = "",
    page: int = 0, page_size: int = PAGE_SIZE,
):
    """Registry senders NOT yet assigned to this group (add picker), paginated."""
    assigned = select(SenderGroupAssignment.allowed_sender_id).where(
        SenderGroupAssignment.source_chat_id == source_chat_id
    )
    base = select(AllowedSender).where(
        AllowedSender.bot_id == bot_id, ~AllowedSender.id.in_(assigned)
    )
    if q:
        base = base.where(AllowedSender.username.startswith(_norm_q(q)))
    return _paginate(session, base, page, page_size)


def group_sender_counts(session: Session, bot_id: int) -> dict[int, int]:
    """{source_chat_id: number of assigned senders} for the bot (one grouped query)."""
    rows = session.exec(
        select(
            SenderGroupAssignment.source_chat_id, func.count()
        )
        .join(
            AllowedSender, AllowedSender.id == SenderGroupAssignment.allowed_sender_id
        )
        .where(AllowedSender.bot_id == bot_id)
        .group_by(SenderGroupAssignment.source_chat_id)
    ).all()
    return {src: cnt for src, cnt in rows}


def count_senders(session: Session, bot_id: int) -> int:
    """Number of registry senders for the bot."""
    return session.exec(
        select(func.count()).select_from(
            select(AllowedSender).where(AllowedSender.bot_id == bot_id).subquery()
        )
    ).one()


def _is_bot_source(session: Session, bot_id: int, source_chat_id: int) -> bool:
    return session.exec(
        select(Route.source_chat_id).where(
            Route.bot_id == bot_id, Route.source_chat_id == source_chat_id
        )
    ).first() is not None


def add_group_sender(
    session: Session, bot_id: int, source_chat_id: int, sender_id: int
) -> bool:
    """Assign one registry sender to one source group (idempotent, bot-scoped).

    Returns False on an IDOR/validation miss (sender not the bot's, or the source
    is not a real route source of the bot).
    """
    sender = session.get(AllowedSender, sender_id)
    if not sender or sender.bot_id != bot_id:
        return False
    if not _is_bot_source(session, bot_id, source_chat_id):
        return False
    exists = session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.allowed_sender_id == sender_id,
            SenderGroupAssignment.source_chat_id == source_chat_id,
        )
    ).first()
    if not exists:
        session.add(
            SenderGroupAssignment(
                allowed_sender_id=sender_id, source_chat_id=source_chat_id
            )
        )
        session.commit()
    return True


def add_sender_by_username(
    session: Session, bot_id: int, source_chat_id: int,
    username: str, label: str | None = None,
) -> bool:
    """Assign a sender to a group by username (find-or-create in the registry).

    Convenience for inline per-group add: creates the global AllowedSender if it
    doesn't exist yet (updating its label when given), then assigns it to the
    group. Returns False if the source is not a real route source of the bot.
    """
    if not _is_bot_source(session, bot_id, source_chat_id):
        return False
    sender = add_allowed_sender(session, bot_id, username, label=label)
    add_group_sender(session, bot_id, source_chat_id, sender.id)
    return True


def remove_group_sender(
    session: Session, bot_id: int, source_chat_id: int, sender_id: int
) -> None:
    """Unassign one sender from one source group (bot-scoped)."""
    sender = session.get(AllowedSender, sender_id)
    if not sender or sender.bot_id != bot_id:
        return
    row = session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.allowed_sender_id == sender_id,
            SenderGroupAssignment.source_chat_id == source_chat_id,
        )
    ).first()
    if row:
        session.delete(row)
        session.commit()


# --- Multi-tenant: teams, users, bot visibility ---

def visible_bots(session: Session, team_id: int | None, is_admin: bool) -> list[Bot]:
    """Bots visible to a viewer. Super-admin sees all; a member sees only their
    team's bots (a member with no team sees none)."""
    if is_admin:
        return session.exec(select(Bot)).all()
    if team_id is None:
        return []
    return session.exec(select(Bot).where(Bot.team_id == team_id)).all()


def can_access_bot(bot: Bot | None, team_id: int | None, is_admin: bool) -> bool:
    """Whether a viewer may access a specific bot (super-admin bypass)."""
    if bot is None:
        return False
    if is_admin:
        return True
    return team_id is not None and bot.team_id == team_id


# --- Team CRUD ---

def create_team(session: Session, name: str) -> Team | None:
    """Create a team. Returns None on blank/duplicate name."""
    name = (name or "").strip()
    if not name:
        return None
    if session.exec(select(Team).where(Team.name == name)).first():
        return None
    team = Team(name=name)
    session.add(team)
    session.commit()
    session.refresh(team)
    return team


def list_teams(session: Session) -> list[Team]:
    return session.exec(select(Team).order_by(Team.name)).all()


def delete_team(session: Session, team_id: int) -> bool:
    """Delete a team only if it has no users and no bots. Returns False otherwise."""
    team = session.get(Team, team_id)
    if not team:
        return False
    has_user = session.exec(select(User).where(User.team_id == team_id)).first()
    has_bot = session.exec(select(Bot).where(Bot.team_id == team_id)).first()
    if has_user or has_bot:
        return False
    session.delete(team)
    session.commit()
    return True


# --- User CRUD ---

def get_user_by_username(session: Session, username: str) -> User | None:
    username = (username or "").strip().lower()
    if not username:
        return None
    return session.exec(select(User).where(User.username == username)).first()


def create_user(
    session: Session, username: str, password: str, team_id: int
) -> User | None:
    """Create a team member. Returns None on invalid/duplicate username or
    missing team. Password is PBKDF2-hashed."""
    username = (username or "").strip().lower()
    if not username or not (password or "").strip():
        return None
    if session.get(Team, team_id) is None:
        return None
    if get_user_by_username(session, username):
        return None
    user = User(
        username=username,
        password_hash=hash_password(password),
        team_id=team_id,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user


def list_users(session: Session) -> list[User]:
    return session.exec(select(User).order_by(User.username)).all()


def delete_user(session: Session, user_id: int) -> None:
    user = session.get(User, user_id)
    if user:
        session.delete(user)
        session.commit()


def reset_user_password(session: Session, user_id: int, password: str) -> bool:
    """Set a new password for a user. Returns False if user missing/blank pw."""
    user = session.get(User, user_id)
    if not user or not (password or "").strip():
        return False
    user.password_hash = hash_password(password)
    session.add(user)
    session.commit()
    return True


