"""Webhook single-JOIN gating end-to-end: correct ForwardJobs (real DB, no mocks).

Exercises the receiver up to the DB enqueue; no outbound Telegram call happens
because the worker is not run here.
"""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, ForwardJob, Route, SenderGroupAssignment

SECRET = "hook-secret"


def _seed(tg_bot_id: int):
    """Bot with routes 10->20 (restricted to alice) and 11->21 (open)."""
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=tg_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret=SECRET,
            status="active",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=10, dest_chat_id=20))
        s.add(Route(bot_id=bot.id, source_chat_id=11, dest_chat_id=21))
        alice = AllowedSender(bot_id=bot.id, username="alice")
        bob = AllowedSender(bot_id=bot.id, username="bob")
        s.add(alice)
        s.add(bob)
        s.commit()
        s.refresh(alice)
        # group 10 restricted to alice; group 11 has NO assignment (open)
        s.add(SenderGroupAssignment(allowed_sender_id=alice.id, source_chat_id=10))
        s.commit()
        return bot.id


def _msg(chat, username):
    return {"message": {"chat": {"id": chat}, "from": {"id": 7, "username": username},
                        "message_id": 99, "text": "hi"}}


def _jobs(bot_id, dest):
    with Session(engine) as s:
        return s.exec(
            select(ForwardJob).where(
                ForwardJob.bot_id == bot_id, ForwardJob.dest_chat_id == dest)
        ).all()


def _post(client, bot_id, payload):
    return client.post(
        f"/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        json=payload,
    )


def test_restricted_group_only_forwards_assigned(client):
    bid = _seed(5551)
    # alice is assigned to group 10 -> forwarded to dest 20
    assert _post(client, bid, _msg(10, "alice")).json() == {"ok": True}
    assert len(_jobs(bid, 20)) == 1
    # bob not assigned to group 10 -> blocked
    _post(client, bid, _msg(10, "bob"))
    assert len(_jobs(bid, 20)) == 1  # unchanged


def test_open_group_forwards_everyone(client):
    bid = _seed(5552)
    # group 11 has no assignment -> open -> bob forwarded to dest 21
    _post(client, bid, _msg(11, "bob"))
    assert len(_jobs(bid, 21)) == 1
