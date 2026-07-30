"""Webhook secret verification (real DB rows, no Telegram network).

Only the pre-dispatch branches (unknown bot -> 404, bad secret -> 403) are
exercised, so no outbound Telegram call happens.
"""

from sqlmodel import Session

from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot


def _insert_bot(secret: str) -> int:
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=111,
            username="tester",
            token_encrypted=encrypt_token("123:fake-token"),
            webhook_secret=secret,
            status="active",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        return bot.id


def test_unknown_bot_returns_404(client):
    r = client.post("/webhook/999999", json={})
    assert r.status_code == 404


def test_bad_secret_returns_403(client):
    bot_id = _insert_bot(secret="the-right-secret")
    r = client.post(
        f"/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": "wrong-secret"},
        json={},
    )
    assert r.status_code == 403
