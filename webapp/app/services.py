"""Bot lifecycle & route operations (DB + Telegram side effects)."""

from __future__ import annotations

import logging
import secrets

from sqlmodel import Session, select

from app import botcache, telegram_api
from app.crypto import decrypt_token, encrypt_token
from app.forwarding import normalize_username
from app.models import AllowedSender, Bot, ForwardJob, Route
from app.pw import hash_password

logger = logging.getLogger(__name__)


class DuplicateBotError(Exception):
    """Raised when the same Telegram bot is added twice."""


async def add_bot(
    session: Session, token: str, access_password: str | None = None
) -> Bot:
    """Validate a token, store it encrypted, and register its webhook.

    ``access_password`` (optional) locks the bot's page behind that password.
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
    for allowed in session.exec(
        select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    ).all():
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
) -> list[Route]:
    """Create one directed route (or two, if bidirectional)."""
    created: list[Route] = []
    pairs = [(source_chat_id, dest_chat_id)]
    if bidirectional:
        pairs.append((dest_chat_id, source_chat_id))

    for src, dst in pairs:
        exists = session.exec(
            select(Route).where(
                Route.bot_id == bot_id,
                Route.source_chat_id == src,
                Route.dest_chat_id == dst,
            )
        ).first()
        if exists:
            continue
        route = Route(bot_id=bot_id, source_chat_id=src, dest_chat_id=dst)
        session.add(route)
        created.append(route)
    session.commit()
    return created


def delete_route(session: Session, route_id: int, bot_id: int | None = None) -> None:
    route = session.get(Route, route_id)
    # Scope the delete to the bot in the URL to avoid cross-bot deletion (IDOR).
    if route and (bot_id is None or route.bot_id == bot_id):
        session.delete(route)
        session.commit()


def add_allowed_sender(
    session: Session,
    bot_id: int,
    source_chat_id: int,
    username: str,
    both_ways: bool = False,
    label: str | None = None,
) -> list[AllowedSender]:
    """Add a username to a source group's allowlist (normalized, deduped).

    ``both_ways`` also adds it to the group's bridge partner(s) — the dest chats
    it forwards to — so a bidirectional bridge is covered in one action.
    ``label`` (optional) sets the display name; on an existing row it updates it.
    """
    username = normalize_username(username)
    label = (label or "").strip() or None
    targets = {source_chat_id}
    if both_ways:
        dests = session.exec(
            select(Route.dest_chat_id).where(
                Route.bot_id == bot_id, Route.source_chat_id == source_chat_id
            )
        ).all()
        targets.update(dests)

    created: list[AllowedSender] = []
    for chat_id in targets:
        exists = session.exec(
            select(AllowedSender).where(
                AllowedSender.bot_id == bot_id,
                AllowedSender.source_chat_id == chat_id,
                AllowedSender.username == username,
            )
        ).first()
        if exists:
            if label is not None:
                exists.label = label
                session.add(exists)
            continue
        row = AllowedSender(
            bot_id=bot_id, source_chat_id=chat_id, username=username, label=label
        )
        session.add(row)
        created.append(row)
    session.commit()
    return created


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
        session.delete(row)
        session.commit()


