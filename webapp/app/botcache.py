"""Cached ExtBot instances (built once, with rate limiting) + the send function.

Building a fresh Bot per update would call getMe every time; caching an
initialized ExtBot avoids that and lets the AIORateLimiter pace/retry sends
(30/s overall, 20/min per group, retries on 429).
"""

from __future__ import annotations

import logging

import json

from sqlmodel import Session, select
from telegram import MessageEntity
from telegram.error import BadRequest, Forbidden
from telegram.ext import AIORateLimiter, ExtBot

from app.config import get_settings
from app.crypto import decrypt_token
from app.db import engine
from app.models import Bot

logger = logging.getLogger(__name__)

_bots: dict[int, ExtBot] = {}
_tokens: dict[int, str] = {}


def _token_for(bot_id: int) -> str | None:
    token = _tokens.get(bot_id)
    if token is None:
        with Session(engine) as s:
            row = s.get(Bot, bot_id)
            if not row:
                return None
            token = decrypt_token(row.token_encrypted)
            _tokens[bot_id] = token
    return token


async def _get_bot(bot_id: int) -> ExtBot | None:
    bot = _bots.get(bot_id)
    if bot is not None:
        return bot
    token = _token_for(bot_id)
    if token is None:
        return None
    s = get_settings()
    # Configurable safety margin (defaults 25/s overall, 1 msg / 3.5s per group),
    # plus automatic 429 retries.
    limiter = AIORateLimiter(
        overall_max_rate=s.rate_overall_per_sec,
        overall_time_period=1.0,
        group_max_rate=1,
        group_time_period=s.rate_group_interval_sec,
        max_retries=3,
    )
    bot = ExtBot(token, rate_limiter=limiter)
    await bot.initialize()  # single getMe for the lifetime of the process
    _bots[bot_id] = bot
    return bot


class PermanentSendError(Exception):
    """A send that will never succeed on retry (undeliverable message/chat)."""

    permanent = True


def _entities(json_str: str | None, bot: ExtBot):
    if not json_str:
        return None
    return [MessageEntity.de_json(e, bot) for e in json.loads(json_str)]


async def send_job(job: dict) -> None:
    """Deliver one outbox job.

    Transient errors propagate (worker retries with backoff). Telegram
    BadRequest/Forbidden (e.g. "message can't be copied", bot kicked, chat not
    found) are permanent -> raised as PermanentSendError so the worker fails the
    job fast instead of blocking the destination's queue.
    """
    bot = await _get_bot(job["bot_id"])
    if bot is None:
        raise RuntimeError(f"bot {job['bot_id']} not found / not decryptable")

    kind = job["kind"]
    mt = job.get("dest_thread_id")  # forum topic (None = General/normal)
    try:
        if kind == "text":
            await bot.send_message(
                chat_id=job["dest_chat_id"],
                text=job["text"],
                entities=_entities(job.get("entities_json"), bot),
                message_thread_id=mt,
            )
        elif kind == "copy_caption":
            await bot.copy_message(
                chat_id=job["dest_chat_id"],
                from_chat_id=job["from_chat_id"],
                message_id=job["message_id"],
                caption=job.get("caption"),
                caption_entities=_entities(job.get("caption_entities_json"), bot),
                message_thread_id=mt,
            )
        else:  # "copy"
            await bot.copy_message(
                chat_id=job["dest_chat_id"],
                from_chat_id=job["from_chat_id"],
                message_id=job["message_id"],
                message_thread_id=mt,
            )
    except (BadRequest, Forbidden) as exc:
        raise PermanentSendError(str(exc)) from exc


async def evict(bot_id: int) -> None:
    _tokens.pop(bot_id, None)
    bot = _bots.pop(bot_id, None)
    if bot is not None:
        try:
            await bot.shutdown()
        except Exception as exc:
            logger.warning("bot %s shutdown failed: %s", bot_id, exc)


async def shutdown_all() -> None:
    for bot_id in list(_bots):
        await evict(bot_id)
