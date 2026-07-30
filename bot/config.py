"""Configuration loading and validation.

Loads the bot token from a `.env` file and the forwarding routes from a
YAML file. Fails fast with clear error messages when something is missing
or malformed, so misconfiguration is caught at startup instead of at runtime.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from logging.handlers import RotatingFileHandler
from pathlib import Path

import yaml
from dotenv import load_dotenv

# Default file locations relative to the project root.
_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ENV_PATH = _ROOT / ".env"
DEFAULT_ROUTES_PATH = _ROOT / "config" / "routes.yaml"

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


@dataclass
class Config:
    """Validated bot configuration."""

    token: str
    # Each bridge is a pair of chat ids that mirror messages both ways.
    bridges: list[tuple[int, int]] = field(default_factory=list)
    log_level: str = "INFO"


def load_config(
    env_path: Path | str = DEFAULT_ENV_PATH,
    routes_path: Path | str = DEFAULT_ROUTES_PATH,
) -> Config:
    """Load and validate configuration from `.env` and routes YAML.

    Raises ``ValueError`` with an actionable message on any problem.
    """
    env_path = Path(env_path)
    routes_path = Path(routes_path)

    # --- Token (secret) -------------------------------------------------
    load_dotenv(env_path, override=True)
    token = (os.getenv("BOT_TOKEN") or "").strip()
    if not token:
        raise ValueError(
            f"BOT_TOKEN is missing. Copy .env.example to {env_path} and set "
            "BOT_TOKEN to the token from @BotFather."
        )

    # --- Routes ---------------------------------------------------------
    if not routes_path.exists():
        raise ValueError(
            f"Routes file not found: {routes_path}. Copy "
            "config/routes.example.yaml to config/routes.yaml and edit it."
        )

    with routes_path.open("r", encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}

    if not isinstance(data, dict):
        raise ValueError(f"{routes_path} must contain a YAML mapping at the top level.")

    raw_bridges = data.get("bridges") or []
    if not isinstance(raw_bridges, list) or not raw_bridges:
        raise ValueError(
            f"No bridges defined in {routes_path}. Add at least one pair under "
            "'bridges', e.g. `- [-1001111111111, -1002222222222]`."
        )

    bridges = _parse_bridges(raw_bridges, routes_path)

    log_level = str(data.get("log_level", "INFO")).upper()
    if log_level not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"Invalid log_level '{log_level}' in {routes_path}. "
            f"Use one of: {', '.join(sorted(_VALID_LOG_LEVELS))}."
        )

    return Config(token=token, bridges=bridges, log_level=log_level)


def _parse_bridges(raw_bridges: list, routes_path: Path) -> list[tuple[int, int]]:
    """Validate each bridge is a pair of two distinct integer chat ids."""
    bridges: list[tuple[int, int]] = []
    for i, pair in enumerate(raw_bridges, start=1):
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise ValueError(
                f"Bridge #{i} in {routes_path} must be a pair of two chat ids, "
                f"got: {pair!r}."
            )
        try:
            a, b = int(pair[0]), int(pair[1])
        except (TypeError, ValueError):
            raise ValueError(
                f"Bridge #{i} in {routes_path} has a non-integer chat id: {pair!r}."
            )
        if a == b:
            raise ValueError(
                f"Bridge #{i} in {routes_path} links a group to itself ({a}). "
                "The two chat ids must be different."
            )
        bridges.append((a, b))
    return bridges


def setup_logging(level: str = "INFO") -> None:
    """Configure logging to console + a rotating file (bot.log)."""
    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    formatter = logging.Formatter(fmt)

    console = logging.StreamHandler()
    console.setFormatter(formatter)

    file_handler = RotatingFileHandler(
        _ROOT / "bot.log", maxBytes=1_000_000, backupCount=3, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))
    root.handlers.clear()
    root.addHandler(console)
    root.addHandler(file_handler)

    # Quiet noisy third-party loggers.
    logging.getLogger("httpx").setLevel(logging.WARNING)
