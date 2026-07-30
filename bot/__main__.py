"""Entrypoint: build the Application and run long polling.

Run with: ``python -m bot``
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import (
    AIORateLimiter,
    Application,
    CommandHandler,
    MessageHandler,
    filters,
)

from bot.config import load_config, setup_logging
from bot.handlers import (
    cmd_chatid,
    cmd_start,
    cmd_status,
    forward_handler,
)
from bot.router import RouteTable

logger = logging.getLogger(__name__)


def main() -> None:
    config = load_config()
    setup_logging(config.log_level)

    routes = RouteTable.from_bridges(config.bridges)
    logger.info(
        "Loaded %d bridge(s), %d directed route(s): sources=%s",
        len(config.bridges),
        len(routes),
        routes.sources,
    )

    application = (
        Application.builder()
        .token(config.token)
        .rate_limiter(AIORateLimiter())
        .build()
    )
    application.bot_data["routes"] = routes

    # Commands first so they are not swallowed by the message handler.
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("chatid", cmd_chatid))
    application.add_handler(CommandHandler("status", cmd_status))

    # Forward every non-command message posted in a group/supergroup.
    application.add_handler(
        MessageHandler(filters.ChatType.GROUPS & ~filters.COMMAND, forward_handler)
    )

    logger.info("Bot starting (long polling)...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
