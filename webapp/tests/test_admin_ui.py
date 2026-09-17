"""Super-admin account management UI (TestClient, real DB, no mocks)."""

from sqlmodel import Session, select

from app import services
from app.db import engine
from app.models import Bot, Team, User
from app.crypto import encrypt_token


def _login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=False,
    )


def _admin(client):
    _login(client, "testuser", "testpass")


def test_admin_page_requires_login(client):
    r = client.get("/admin", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_admin_page_renders_for_super_admin(client):
    _admin(client)
    r = client.get("/admin")
    assert r.status_code == 200 and "Teams" in r.text and "Users" in r.text


def test_admin_page_forbidden_for_member(client):
    with Session(engine) as s:
        team = services.create_team(s, "MemTeam")
        services.create_user(s, "member1", "memberpass1", team.id)
    _login(client, "member1", "memberpass1")
    assert client.get("/admin", follow_redirects=False).status_code == 403


def test_super_admin_can_create_team_and_user(client):
    _admin(client)
    client.post("/admin/teams", data={"name": "SalesTeam"}, follow_redirects=False)
    with Session(engine) as s:
        team = s.exec(select(Team).where(Team.name == "SalesTeam")).first()
        assert team is not None
    client.post(
        "/admin/users",
        data={"username": "sale1", "password": "salepass1", "team_id": team.id},
        follow_redirects=False,
    )
    # the created member can now log in
    r = _login(client, "sale1", "salepass1")
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_create_user_short_password_rejected(client):
    _admin(client)
    client.post("/admin/teams", data={"name": "ShortPw"}, follow_redirects=False)
    with Session(engine) as s:
        team = s.exec(select(Team).where(Team.name == "ShortPw")).first()
    r = client.post(
        "/admin/users",
        data={"username": "shorty", "password": "ab", "team_id": team.id},
        follow_redirects=False,
    )
    assert "pw_short" in r.headers["location"]
    with Session(engine) as s:
        assert services.get_user_by_username(s, "shorty") is None


def test_delete_nonempty_team_blocked(client):
    _admin(client)
    with Session(engine) as s:
        team = services.create_team(s, "HasBot")
        s.add(Bot(
            telegram_bot_id=9101, username="hb",
            token_encrypted=encrypt_token("1:x"), webhook_secret="s",
            team_id=team.id,
        ))
        s.commit()
        tid = team.id
    r = client.post(f"/admin/teams/{tid}/delete", follow_redirects=False)
    assert "team_not_empty" in r.headers["location"]
    with Session(engine) as s:
        assert s.get(Team, tid) is not None  # still there


def test_reset_password(client):
    _admin(client)
    with Session(engine) as s:
        team = services.create_team(s, "ResetTeam")
        user = services.create_user(s, "resetme", "oldpass12", team.id)
        uid = user.id
    client.post(
        f"/admin/users/{uid}/password", data={"password": "newpass12"},
        follow_redirects=False,
    )
    # new works, old fails
    client.post("/logout", follow_redirects=False)
    assert _login(client, "resetme", "newpass12").headers["location"] == "/"
    client.post("/logout", follow_redirects=False)
    assert "error" in _login(client, "resetme", "oldpass12").headers["location"]
