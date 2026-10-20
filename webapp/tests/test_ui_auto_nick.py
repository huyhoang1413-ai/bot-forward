"""Auto-nick toggle + captured-names page via the admin UI (real DB, no mocks)."""

from sqlmodel import Session

from app import services
from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot, SenderProfile


def _admin(client):
    client.post("/login", data={"username": "testuser", "password": "testpass"},
                follow_redirects=False)


def _make_bot(tg_id: int) -> int:
    with Session(engine) as s:
        bot = Bot(telegram_bot_id=tg_id, username="u",
                  token_encrypted=encrypt_token("1:x"), webhook_secret="s")
        s.add(bot)
        s.commit()
        s.refresh(bot)
        return bot.id


def test_toggle_auto_nick_persists(client):
    _admin(client)
    bid = _make_bot(8601)
    client.post(f"/bots/{bid}/auto-nick", data={"auto_nick": "1"}, follow_redirects=False)
    with Session(engine) as s:
        assert s.get(Bot, bid).auto_nick is True
    client.post(f"/bots/{bid}/auto-nick", data={}, follow_redirects=False)  # unchecked
    with Session(engine) as s:
        assert s.get(Bot, bid).auto_nick is False


def test_names_page_lists_and_overrides(client):
    _admin(client)
    bid = _make_bot(8602)
    with Session(engine) as s:
        services.capture_sender(s, bid, 901, "Alice", "aliceuser")
    r = client.get(f"/bots/{bid}/names")
    assert r.status_code == 200 and "Alice" in r.text
    # set an override
    with Session(engine) as s:
        pid = services.list_profiles(s, bid)[0][0].id
    client.post(f"/bots/{bid}/names/{pid}/label", data={"label": "Boss"},
                follow_redirects=False)
    with Session(engine) as s:
        assert s.get(SenderProfile, pid).label_override == "Boss"


def test_names_requires_login(client):
    r = client.get("/bots/1/names", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
