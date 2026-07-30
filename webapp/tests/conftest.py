"""Test setup: real SQLite temp DB, real crypto, no network, no mocks.

Environment must be configured BEFORE importing the app modules, so this runs
at import time (pytest imports conftest first).
"""

from __future__ import annotations

import os
import tempfile

from cryptography.fernet import Fernet

_tmp = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
_tmp.close()
_db_path = _tmp.name.replace("\\", "/")  # sqlite URL needs forward slashes on Windows

os.environ.setdefault("ADMIN_PASSWORD", "testpass")
os.environ.setdefault("SESSION_SECRET", "test-session-secret-value-long")
os.environ.setdefault("BOT_TOKEN_KEK", Fernet.generate_key().decode())
os.environ["DATABASE_URL"] = f"sqlite:///{_db_path}"
os.environ.setdefault("PUBLIC_URL", "https://example.com")
os.environ.setdefault("ENVIRONMENT", "dev")
# Do not hit Telegram during tests.
os.environ["RESYNC_WEBHOOKS_ON_STARTUP"] = "false"

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.db import create_db_and_tables  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _create_tables():
    create_db_and_tables()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c
