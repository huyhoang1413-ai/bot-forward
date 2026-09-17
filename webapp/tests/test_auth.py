"""Auth guard + login flow via real HTTP (TestClient), no mocks."""

from sqlmodel import Session

from app import services
from app.db import engine


def test_protected_page_redirects_to_login(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/login"


def test_login_page_is_public(client):
    r = client.get("/login")
    assert r.status_code == 200


def test_wrong_password_redirects_with_error(client):
    r = client.post(
        "/login", data={"username": "testuser", "password": "nope"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]


def test_wrong_username_redirects_with_error(client):
    r = client.post(
        "/login", data={"username": "hacker", "password": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert "error" in r.headers["location"]


def test_correct_credentials_grant_access(client):
    r = client.post(
        "/login", data={"username": "testuser", "password": "testpass"},
        follow_redirects=False,
    )
    assert r.status_code == 303
    assert r.headers["location"] == "/"
    # Session cookie now set on this client -> dashboard reachable.
    r2 = client.get("/", follow_redirects=False)
    assert r2.status_code == 200


def test_db_user_can_login(client):
    with Session(engine) as s:
        team = services.create_team(s, "LoginTeam")
        services.create_user(s, "member_x", "memberpass1", team.id)
    r = client.post(
        "/login", data={"username": "member_x", "password": "memberpass1"},
        follow_redirects=False,
    )
    assert r.status_code == 303 and r.headers["location"] == "/"
    assert client.get("/", follow_redirects=False).status_code == 200
    # a member is NOT super-admin -> /admin forbidden
    assert client.get("/admin", follow_redirects=False).status_code == 403


def test_logout_clears_session(client):
    client.post("/login", data={"username": "testuser", "password": "testpass"},
                follow_redirects=False)
    assert client.get("/", follow_redirects=False).status_code == 200
    client.post("/logout", follow_redirects=False)
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"
