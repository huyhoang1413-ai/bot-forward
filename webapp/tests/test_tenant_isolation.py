"""Cross-team isolation / IDOR matrix via real HTTP (TestClient), no mocks."""

from sqlmodel import Session

from app import services
from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot, Route

PW = "teampass123"


def _seed(team_name, uname, tg_id, bot_username, source=10, dest=20):
    """Create a team + a member + a bot (owned by the team) + one route."""
    with Session(engine) as s:
        team = services.create_team(s, team_name)
        user = services.create_user(s, uname, PW, team.id)
        bot = Bot(
            telegram_bot_id=tg_id, username=bot_username,
            token_encrypted=encrypt_token("1:x"), webhook_secret="s",
            team_id=team.id,
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=source, dest_chat_id=dest))
        s.commit()
        return team.id, user.id, bot.id


def _login(client, username, password):
    return client.post(
        "/login", data={"username": username, "password": password},
        follow_redirects=False,
    )


def test_dashboard_is_team_scoped(client):
    _seed("Alpha", "alice_a", 9001, "alphabot")
    _seed("Beta", "bob_b", 9002, "betabot")
    _login(client, "alice_a", PW)
    body = client.get("/").text
    assert "alphabot" in body and "betabot" not in body


def test_member_cannot_open_other_teams_bot(client):
    _seed("Gamma", "gina_g", 9003, "gammabot")
    _, _, other_bot = _seed("Delta", "dan_d", 9004, "deltabot")
    _login(client, "gina_g", PW)  # gina is in Gamma
    r = client.get(f"/bots/{other_bot}", follow_redirects=False)  # Delta's bot
    assert r.status_code == 403


def test_member_cannot_mutate_other_teams_bot(client):
    _seed("Eps", "eve_e", 9005, "epsbot")
    _, _, other = _seed("Zeta", "zoe_z", 9006, "zetabot")
    _login(client, "eve_e", PW)
    # every /bots/{id} entrypoint must reject a cross-team member with 403
    assert client.get(f"/bots/{other}/senders", follow_redirects=False).status_code == 403
    assert client.get(f"/bots/{other}/groups/10/senders", follow_redirects=False).status_code == 403
    assert client.post(f"/bots/{other}/routes", data={}, follow_redirects=False).status_code == 403
    assert client.post(f"/bots/{other}/routes/1/edit", data={}, follow_redirects=False).status_code == 403
    assert client.post(f"/bots/{other}/delete", follow_redirects=False).status_code == 403
    assert client.post(f"/bots/{other}/password", data={}, follow_redirects=False).status_code == 403
    assert client.post(
        f"/bots/{other}/groups/10/senders-inline/add", data={"username": "x"},
        follow_redirects=False,
    ).status_code == 403


def test_member_can_access_own_bot(client):
    _, _, own = _seed("Eta", "hank_h", 9007, "etabot")
    _login(client, "hank_h", PW)
    assert client.get(f"/bots/{own}", follow_redirects=False).status_code == 200
    assert client.get(f"/bots/{own}/senders", follow_redirects=False).status_code == 200


def test_super_admin_sees_and_accesses_all(client):
    _, _, a = _seed("Theta", "tom_t", 9008, "thetabot")
    _, _, b = _seed("Iota", "ian_i", 9009, "iotabot")
    _login(client, "testuser", "testpass")  # .env super-admin
    body = client.get("/").text
    assert "thetabot" in body and "iotabot" in body
    assert client.get(f"/bots/{a}", follow_redirects=False).status_code == 200
    assert client.get(f"/bots/{b}", follow_redirects=False).status_code == 200
