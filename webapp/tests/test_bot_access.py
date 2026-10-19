"""Per-bot access password gate via real HTTP (TestClient, no mocks).

The per-bot password locks a bot for TEAM MEMBERS; the super-admin bypasses it.
"""

from sqlmodel import Session

from app import services
from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot
from app.pw import hash_password

MEMBER_PW = "memberpass1"


def _admin_login(client):
    r = client.post("/login", data={"username": "testuser", "password": "testpass"},
                    follow_redirects=False)
    assert r.status_code == 303


def _member_bot(client, telegram_bot_id, bot_password=None):
    """Create a team + member + a bot owned by that team (optional lock), then
    log the client in as the member. Returns the bot id."""
    uname = f"m{telegram_bot_id}"
    with Session(engine) as s:
        team = services.create_team(s, f"T{telegram_bot_id}")
        services.create_user(s, uname, MEMBER_PW, team.id)
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
            team_id=team.id,
            access_password_hash=hash_password(bot_password) if bot_password else None,
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        bid = bot.id
    client.post("/login", data={"username": uname, "password": MEMBER_PW},
                follow_redirects=False)
    return bid


def test_bot_without_password_opens_directly(client):
    bid = _member_bot(client, 7001)
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 200


def test_locked_bot_redirects_member_to_unlock(client):
    bid = _member_bot(client, 7002, bot_password="botpass")
    r = client.get(f"/bots/{bid}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/bots/{bid}/unlock"


def test_wrong_password_stays_locked(client):
    bid = _member_bot(client, 7003, bot_password="botpass")
    r = client.post(f"/bots/{bid}/unlock", data={"password": "nope"}, follow_redirects=False)
    assert r.status_code == 303 and "error" in r.headers["location"]
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 303


def test_correct_password_unlocks_for_session(client):
    bid = _member_bot(client, 7004, bot_password="botpass")
    r = client.post(f"/bots/{bid}/unlock", data={"password": "botpass"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/bots/{bid}"
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 200


def test_locked_bot_mutation_is_blocked_for_member(client):
    bid = _member_bot(client, 7005, bot_password="botpass")
    r = client.post(
        f"/bots/{bid}/routes",
        data={"source_chat_id": "10", "dest_chat_id": "20"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == f"/bots/{bid}/unlock"


def test_super_admin_bypasses_per_bot_password(client):
    # a locked bot (any team) opens for the super-admin without the bot password
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=7006, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
            access_password_hash=hash_password("secretlock"),
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        bid = bot.id
    _admin_login(client)
    assert client.get(f"/bots/{bid}", follow_redirects=False).status_code == 200
