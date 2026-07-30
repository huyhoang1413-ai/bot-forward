"""Application settings loaded from environment (and optional .env).

Required secrets have no default, so a missing one fails fast at startup.
"""

from __future__ import annotations

from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- Secrets (required) ---
    admin_password: str          # single admin login password
    session_secret: str          # signs the session cookie
    bot_token_kek: str           # Fernet key (44-char urlsafe base64) to encrypt bot tokens

    # --- Optional / defaults ---
    database_url: str = "sqlite:///./data/app.db"
    public_url: str = ""         # e.g. https://bots.example.com ; required for webhooks
    environment: str = "dev"     # "dev" | "prod"
    resync_webhooks_on_startup: bool = True  # re-apply webhooks for active bots on boot

    # --- Send rate limits (safety margin below Telegram's ~30/s + 20/min per group) ---
    rate_overall_per_sec: float = 25.0       # global cap across all bots/chats
    rate_group_interval_sec: float = 3.5     # min seconds between sends to the SAME group


@lru_cache
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
