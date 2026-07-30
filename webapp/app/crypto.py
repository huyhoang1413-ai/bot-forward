"""Symmetric encryption for bot tokens at rest (Fernet / AES-128 + HMAC)."""

from __future__ import annotations

from functools import lru_cache

from cryptography.fernet import Fernet

from app.config import get_settings


@lru_cache
def _fernet() -> Fernet:
    return Fernet(get_settings().bot_token_kek.encode())


def encrypt_token(plaintext: str) -> bytes:
    """Encrypt a bot token; returns ciphertext bytes to store in the DB."""
    return _fernet().encrypt(plaintext.encode())


def decrypt_token(ciphertext: bytes) -> str:
    """Decrypt a stored token back to plaintext (in-memory use only)."""
    return _fernet().decrypt(ciphertext).decode()


def generate_kek() -> str:
    """Generate a new KEK. Run once, store in env BOT_TOKEN_KEK, back it up."""
    return Fernet.generate_key().decode()
