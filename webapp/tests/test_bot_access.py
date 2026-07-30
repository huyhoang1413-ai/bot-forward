"""Per-bot access password gate via real HTTP (TestClient, no mocks)."""

from sqlmodel import Session

from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot
from app.pw import hash_password


def _login(client):
    r = client.post("/login", data={"password": "testpass"}, follow_redirects=False)
    assert r.status_code == 303


def _make_bot(telegram_bot_id: int, password: str | None = None) -> int:
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
            access_password_hash=hash_password(password) if password else None,
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        return bot.id


def test_bot_without_password_opens_directly(client):
    _login(client)
    bid = _make_bot(7001)
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 200


def test_locked_bot_redirects_to_unlock(client):
    _login(client)
    bid = _make_bot(7002, password="botpass")
    r = client.get(f"/bots/{bid}", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/bots/{bid}/unlock"


def test_wrong_password_stays_locked(client):
    _login(client)
    bid = _make_bot(7003, password="botpass")
    r = client.post(f"/bots/{bid}/unlock", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 303 and "error" in r.headers["location"]
    r2 = client.get(f"/bots/{bid}", follow_redirects=False)
    assert r2.status_code == 303  # still locked


def test_correct_password_unlocks_for_session(client):
    _login(client)
    bid = _make_bot(7004, password="botpass")
    r = client.post(f"/bots/{bid}/unlock", data={"password": "botpass"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/bots/{bid}"
    # Subsequent access is allowed without re-entering.
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 200


def test_locked_bot_mutation_is_blocked(client):
    _login(client)
    bid = _make_bot(7005, password="botpass")
    r = client.post(
        f"/bots/{bid}/routes",
        data={"source_chat_id": "10", "dest_chat_id": "20"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/bots/{bid}/unlock"
