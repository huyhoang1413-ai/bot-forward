"""Auth guard + login flow via real HTTP (TestClient), no mocks."""


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
