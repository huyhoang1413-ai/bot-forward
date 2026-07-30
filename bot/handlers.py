"""Telegram update handlers: forwarding logic + utility commands."""

from __future__ import annotations

import logging
import time

from telegram import Update
from telegram.ext import ContextTypes

from bot.router import RouteTable

logger = logging.getLogger(__name__)

# Bot start time, used by /status for uptime.
_START_TS = time.monotonic()


def _routes(context: ContextTypes.DEFAULT_TYPE) -> RouteTable:
    return context.bot_data["routes"]


async def forward_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Copy an incoming group message to every bridged destination.

    ``copy_message`` produces a clean copy (no "Forwarded from" header) and
    transparently handles text, photos, videos, documents, stickers, etc.
    """
    msg = update.effective_message
    chat = update.effective_chat
    if msg is None or chat is None:
        return

    # Loop guard: never re-forward the bot's own copies (prevents A<->B loops).
    if update.effective_user and update.effective_user.id == context.bot.id:
        return

    dests = _routes(context).destinations(chat.id)
    if not dests:
        return  # message from a chat that is not a configured source

    for dest in dests:
        try:
            await context.bot.copy_message(
                chat_id=dest,
                from_chat_id=chat.id,
                message_id=msg.message_id,
            )
        except Exception as exc:  # keep the bot alive on a single failed copy
            logger.error("copy %s -> %s failed: %s", chat.id, dest, exc)


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Bot forward hai chieu dang chay.\n"
        "Them bot lam admin o ca hai nhom, roi dung /chatid de lay chat id "
        "va them vao config/routes.yaml.\n"
        "Lenh: /chatid, /status"
    )


async def cmd_chatid(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    chat = update.effective_chat
    await update.effective_message.reply_text(f"chat_id: {chat.id}")


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uptime = int(time.monotonic() - _START_TS)
    routes = _routes(context)
    await update.effective_message.reply_text(
        f"Uptime: {uptime}s\n"
        f"Sources: {len(routes.sources)}\n"
        f"Directed routes: {len(routes)}"
    )
