"""Per-group sender assignment via incremental UI endpoints (real DB, no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, Route, SenderGroupAssignment


def _login(client):
    r = client.post("/login", data={"username": "testuser", "password": "testpass"},
                    follow_redirects=False)
    assert r.status_code == 303


def _make_bot(telegram_bot_id: int, source: int = 10, dest: int = 20):
    """Bot with one route + two global senders. Returns (bot_id, [sender_ids])."""
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=source, dest_chat_id=dest))
        a = AllowedSender(bot_id=bot.id, username="alice")
        b = AllowedSender(bot_id=bot.id, username="bob")
        s.add(a)
        s.add(b)
        s.commit()
        return bot.id, [a.id, b.id]


def _assigned(bot_id, source):
    with Session(engine) as s:
        own = [r.id for r in s.exec(
            select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()]
        return {
            x.allowed_sender_id
            for x in s.exec(
                select(SenderGroupAssignment).where(
                    SenderGroupAssignment.source_chat_id == source,
                    SenderGroupAssignment.allowed_sender_id.in_(own or [-1]),
                )
            ).all()
        }


def test_group_page_renders(client):
    _login(client)
    bid, _ = _make_bot(8201)
    r = client.get(f"/bots/{bid}/groups/10/senders")
    assert r.status_code == 200
    # picker only shows results after a search; search surfaces the unassigned one
    r2 = client.get(f"/bots/{bid}/groups/10/senders?q=alice")
    assert r2.status_code == 200 and "alice" in r2.text


def test_add_and_remove_group_sender_via_ui(client):
    _login(client)
    bid, ids = _make_bot(8202)
    r = client.post(f"/bots/{bid}/groups/10/senders/{ids[0]}/add", follow_redirects=False)
    assert r.status_code == 303
    assert _assigned(bid, 10) == {ids[0]}
    # remove
    r = client.post(f"/bots/{bid}/groups/10/senders/{ids[0]}/remove", follow_redirects=False)
    assert r.status_code == 303
    assert _assigned(bid, 10) == set()


def test_group_add_requires_login(client):
    r = client.post("/bots/1/groups/10/senders/1/add", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_group_add_ignores_cross_bot_sender(client):
    _login(client)
    bid_a, _ = _make_bot(8203, source=10, dest=20)
    _, ids_b = _make_bot(8204, source=30, dest=40)  # another bot's senders
    r = client.post(
        f"/bots/{bid_a}/groups/10/senders/{ids_b[0]}/add", follow_redirects=False
    )
    assert r.status_code == 303
    assert _assigned(bid_a, 10) == set()


def test_group_page_bad_source_redirects_to_bot(client):
    _login(client)
    bid, _ = _make_bot(8205)
    r = client.get(f"/bots/{bid}/groups/999/senders", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/bots/{bid}"


# --- inline management from the bot-detail dropdown ---

def test_inline_add_by_username_and_keep_group_open(client):
    _login(client)
    bid, _ = _make_bot(8206)
    r = client.post(
        f"/bots/{bid}/groups/10/senders-inline/add",
        data={"username": "@Charlie", "label": "C"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == f"/bots/{bid}?g=10#g10"  # group stays open
    # 'charlie' created in registry + assigned to group 10
    with Session(engine) as s:
        row = s.exec(select(AllowedSender).where(
            AllowedSender.bot_id == bid, AllowedSender.username == "charlie")).first()
        assert row is not None and row.id in _assigned(bid, 10)


def test_inline_add_bad_username_redirects_with_error(client):
    _login(client)
    bid, _ = _make_bot(8207)
    r = client.post(
        f"/bots/{bid}/groups/10/senders-inline/add",
        data={"username": "ab"},  # too short
        follow_redirects=False,
    )
    assert r.status_code == 303 and "error=bad_username" in r.headers["location"]


def test_inline_remove(client):
    _login(client)
    bid, ids = _make_bot(8208)
    client.post(f"/bots/{bid}/groups/10/senders/{ids[0]}/add", follow_redirects=False)
    assert _assigned(bid, 10) == {ids[0]}
    r = client.post(
        f"/bots/{bid}/groups/10/senders-inline/{ids[0]}/remove", follow_redirects=False
    )
    assert r.status_code == 303
    assert _assigned(bid, 10) == set()
