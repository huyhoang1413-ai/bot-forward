"""Auto-nickname end-to-end via the webhook (real DB, no network)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot, ForwardJob, Route, SenderProfile

SECRET = "autonick-secret"


def _seed(tg_bot_id: int, auto_nick: bool):
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=tg_bot_id, username="u",
            token_encrypted=encrypt_token("1:x"), webhook_secret=SECRET,
            status="active", auto_nick=auto_nick,
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=10, dest_chat_id=20))  # no allowlist
        s.commit()
        return bot.id


def _msg(chat, uid, first_name, text="hi"):
    return {"message": {
        "chat": {"id": chat},
        "from": {"id": uid, "first_name": first_name, "username": "someone"},
        "message_id": 99, "text": text,
    }}


def _no_from_msg(chat):
    # anonymous admin: sender_chat only, no `from`
    return {"message": {"chat": {"id": chat}, "sender_chat": {"id": chat},
                        "message_id": 99, "text": "hi"}}


def _jobs(bot_id):
    with Session(engine) as s:
        return s.exec(select(ForwardJob).where(ForwardJob.bot_id == bot_id)).all()


def _profiles(bot_id):
    with Session(engine) as s:
        return s.exec(select(SenderProfile).where(SenderProfile.bot_id == bot_id)).all()


def _post(client, bot_id, payload):
    return client.post(
        f"/webhook/{bot_id}",
        headers={"X-Telegram-Bot-Api-Secret-Token": SECRET},
        json=payload,
    )


def test_auto_nick_on_prefixes_first_name(client):
    bid = _seed(7301, auto_nick=True)
    _post(client, bid, _msg(10, 501, "Nguyễn"))
    # captured + forwarded as a labeled text job "[Nguyễn] hi"
    assert len(_profiles(bid)) == 1 and _profiles(bid)[0].first_name == "Nguyễn"
    jobs = _jobs(bid)
    assert len(jobs) == 1 and jobs[0].kind == "text" and jobs[0].text == "[Nguyễn] hi"


def test_auto_nick_capture_once(client):
    bid = _seed(7302, auto_nick=True)
    _post(client, bid, _msg(10, 502, "First"))
    _post(client, bid, _msg(10, 502, "Renamed"))  # capture-once: name frozen
    profs = _profiles(bid)
    assert len(profs) == 1 and profs[0].first_name == "First"


def test_auto_nick_off_plain_copy(client):
    bid = _seed(7303, auto_nick=False)
    _post(client, bid, _msg(10, 503, "Bob"))
    jobs = _jobs(bid)
    assert len(jobs) == 1 and jobs[0].kind == "copy"  # no label prefix
    # still captured (so toggling on later works retroactively)
    assert len(_profiles(bid)) == 1


def test_no_from_message_not_captured(client):
    bid = _seed(7304, auto_nick=True)
    _post(client, bid, _no_from_msg(10))
    assert _profiles(bid) == []          # anonymous -> no capture
    jobs = _jobs(bid)
    assert len(jobs) == 1 and jobs[0].kind == "copy"  # forwarded, unlabeled
