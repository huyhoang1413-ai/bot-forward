"""Topic-aware forwarding end-to-end: webhook -> ForwardJob with dest_thread_id.

Real DB, no network (worker not run). Mirrors test_webhook_query.py.
"""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import Bot, ForwardJob, Route
from app.queue import _job_to_dict

SECRET = "topic-secret"


def _seed(tg_bot_id: int):
    """Bot with a topic route (chat 10 topic 7 -> chat 20 topic 3) and a
    whole-group route (chat 10 -> chat 21)."""
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=tg_bot_id, username="u",
            token_encrypted=encrypt_token("1:x"), webhook_secret=SECRET, status="active",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=10, source_thread_id=7,
                    dest_chat_id=20, dest_thread_id=3))
        s.add(Route(bot_id=bot.id, source_chat_id=10, dest_chat_id=21))  # whole group
        s.commit()
        return bot.id


def _topic_msg(chat, thread, username="alice"):
    return {"message": {
        "chat": {"id": chat}, "from": {"id": 7, "username": username},
        "message_id": 99, "text": "hi",
        "is_topic_message": True, "message_thread_id": thread,
    }}


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


def test_topic_message_lands_in_mapped_topic(client):
    bid = _seed(7201)
    assert _post(client, bid, _topic_msg(10, 7)).json() == {"ok": True}
    # topic route -> dest 20 with dest_thread_id 3
    j20 = _jobs(bid, 20)
    assert len(j20) == 1 and j20[0].dest_thread_id == 3
    # whole-group route -> dest 21 with no topic
    j21 = _jobs(bid, 21)
    assert len(j21) == 1 and j21[0].dest_thread_id is None


def test_other_topic_only_matches_whole_group(client):
    bid = _seed(7202)
    _post(client, bid, _topic_msg(10, 9))  # topic 9, not 7
    assert _jobs(bid, 20) == []             # topic-7 route does NOT fire
    assert len(_jobs(bid, 21)) == 1         # whole-group route still does


def test_job_to_dict_carries_dest_thread_id():
    job = ForwardJob(bot_id=1, dest_chat_id=20, dest_thread_id=3, kind="copy",
                     from_chat_id=10, message_id=5)
    assert _job_to_dict(job)["dest_thread_id"] == 3
