"""Registry manager page /bots/{id}/senders (real DB, TestClient, no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot


def _login(client):
    r = client.post("/login", data={"username": "testuser", "password": "testpass"},
                    follow_redirects=False)
    assert r.status_code == 303


def _make_bot(telegram_bot_id: int) -> int:
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        return bot.id


def _rows(bot_id):
    with Session(engine) as s:
        return s.exec(select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()


def test_senders_page_requires_login(client):
    r = client.get("/bots/1/senders", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_add_sender_then_appears(client):
    _login(client)
    bid = _make_bot(8301)
    r = client.post(f"/bots/{bid}/allowed", data={"username": "Alice", "label": "Doby"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/bots/{bid}/senders"
    r = client.get(f"/bots/{bid}/senders")
    assert r.status_code == 200 and "alice" in r.text and "Doby" in r.text


def test_search_filters_results(client):
    _login(client)
    bid = _make_bot(8302)
    with Session(engine) as s:
        for i in range(60):
            s.add(AllowedSender(bot_id=bid, username=f"user{i:03d}"))
        s.add(AllowedSender(bot_id=bid, username="zebra"))
        s.commit()
    # search prefix 'zeb' returns only zebra
    r = client.get(f"/bots/{bid}/senders?q=zeb")
    assert "zebra" in r.text and "user000" not in r.text
    # page 2 exists (61 rows, size 50)
    r2 = client.get(f"/bots/{bid}/senders?page=1")
    assert r2.status_code == 200


def test_remove_sender_via_ui(client):
    _login(client)
    bid = _make_bot(8303)
    client.post(f"/bots/{bid}/allowed", data={"username": "alice"}, follow_redirects=False)
    row_id = _rows(bid)[0].id
    r = client.post(f"/bots/{bid}/allowed/{row_id}/delete", follow_redirects=False)
    assert r.status_code == 303 and _rows(bid) == []
