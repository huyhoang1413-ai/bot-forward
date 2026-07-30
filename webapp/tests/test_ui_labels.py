"""Label-on-allowed-sender management via the merged admin UI (no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, Route


def _login(client):
    r = client.post("/login", data={"username": "testuser", "password": "testpass"}, follow_redirects=False)
    assert r.status_code == 303


def _make_bot(telegram_bot_id: int, source: int = 10, dest: int = 20) -> int:
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
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


def test_add_allowed_with_label_via_ui(client):
    _login(client)
    bid = _make_bot(6101)
    r = client.post(
        f"/bots/{bid}/allowed",
        data={"source_chat_id": "10", "username": "@Alice", "label": "Doby"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    rows = _rows(bid)
    assert [(x.username, x.label) for x in rows] == [("alice", "Doby")]


def test_invalid_label_via_ui_rejected(client):
    _login(client)
    bid = _make_bot(6102)
    r = client.post(
        f"/bots/{bid}/allowed",
        data={"source_chat_id": "10", "username": "alice", "label": "bad[bracket]"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "bad_label" in r.headers["location"]
    assert _rows(bid) == []


def test_edit_label_via_ui(client):
    _login(client)
    bid = _make_bot(6103)
    client.post(f"/bots/{bid}/allowed",
                data={"source_chat_id": "10", "username": "alice"},
                follow_redirects=False)
    row_id = _rows(bid)[0].id
    client.post(f"/bots/{bid}/allowed/{row_id}/label",
                data={"label": "Doby"}, follow_redirects=False)
    assert _rows(bid)[0].label == "Doby"
    # blank clears it
    client.post(f"/bots/{bid}/allowed/{row_id}/label",
                data={"label": ""}, follow_redirects=False)
    assert _rows(bid)[0].label is None


def test_label_routes_require_login(client):
    r = client.post("/bots/1/allowed/1/label", data={"label": "x"},
                    follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"
