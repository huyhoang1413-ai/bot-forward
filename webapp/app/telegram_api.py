"""Thin async wrappers around the Telegram Bot API (python-telegram-bot).

Named ``telegram_api`` (not ``telegram``) to avoid shadowing the PTB package.
"""

from __future__ import annotations

from telegram import Bot

from app.config import get_settings

# Updates we care about for a forwarder: normal + edited messages (commands
# arrive as messages too).
ALLOWED_UPDATES = ["message", "edited_message"]


class InvalidTokenError(Exception):
    """Raised when a token is rejected by Telegram (fake / revoked)."""


async def validate_token(token: str) -> tuple[int, str]:
    """Return (telegram_bot_id, username) if the token is valid.

    Raises InvalidTokenError otherwise.
    """
    try:
        async with Bot(token) as bot:
            me = await bot.get_me()
    except Exception as exc:  # PTB raises InvalidToken / Unauthorized / etc.
        raise InvalidTokenError(str(exc)) from exc
    return me.id, (me.username or "")


def webhook_url(bot_id: int) -> str:
    base = get_settings().public_url.rstrip("/")
    return f"{base}/webhook/{bot_id}"


async def register_webhook(bot_id: int, token: str, secret: str) -> None:
    if not get_settings().public_url:
        raise RuntimeError(
            "PUBLIC_URL is not set; cannot register a Telegram webhook."
        )
    async with Bot(token) as bot:
        await bot.set_webhook(
            url=webhook_url(bot_id),
            secret_token=secret,
            allowed_updates=ALLOWED_UPDATES,
            drop_pending_updates=True,
        )


async def unregister_webhook(token: str) -> None:
    async with Bot(token) as bot:
        await bot.delete_webhook(drop_pending_updates=True)
