"""Allowlist management via the real admin UI (TestClient, no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, Route


def _login(client):
    r = client.post("/login", data={"username": "testuser", "password": "testpass"}, follow_redirects=False)
    assert r.status_code == 303


def _make_bot(telegram_bot_id: int, source: int = 10, dest: int = 20) -> int:
    """Create a bot with one route so `source` is a valid source group."""
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id,
            username="u",
            token_encrypted=encrypt_token("123:fake"),
            webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=source, dest_chat_id=dest))
        s.commit()
        return bot.id


def _rows(bot_id):
    with Session(engine) as s:
        return s.exec(select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()


def test_add_valid_username_via_ui(client):
    _login(client)
    bid = _make_bot(5101)
    r = client.post(
        f"/bots/{bid}/allowed",
        data={"username": "Alice"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert [x.username for x in _rows(bid)] == ["alice"]


def test_invalid_username_via_ui_is_rejected(client):
    _login(client)
    bid = _make_bot(5102)
    r = client.post(
        f"/bots/{bid}/allowed",
        data={"username": "ab"},  # too short
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "bad_username" in r.headers["location"]
    assert _rows(bid) == []


def test_remove_allowed_via_ui(client):
    _login(client)
    bid = _make_bot(5103)
    client.post(
        f"/bots/{bid}/allowed",
        data={"username": "alice"},
        follow_redirects=False,
    )
    row_id = _rows(bid)[0].id
    r = client.post(f"/bots/{bid}/allowed/{row_id}/delete", follow_redirects=False)
    assert r.status_code == 303
    assert _rows(bid) == []


def test_add_allowed_applies_without_a_route(client):
    # The allowlist is global per bot; a sender can be added even with no routes.
    _login(client)
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=5104, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        bid = bot.id
    r = client.post(
        f"/bots/{bid}/allowed",
        data={"username": "alice"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert [x.username for x in _rows(bid)] == ["alice"]


def test_allowed_routes_require_login(client):
    # No login -> redirected to /login.
    r = client.post(
        "/bots/1/allowed",
        data={"username": "alice"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
