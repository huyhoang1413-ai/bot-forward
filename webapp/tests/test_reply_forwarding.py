"""Reply-aware delivery: capture source->dest map, resolve reply at send time,
quote fallback, and 3-day pruning. Real DB; the network boundary is a fake
async send_fn that returns incrementing dest message ids and records each job."""

from __future__ import annotations

import asyncio
from datetime import timedelta

from sqlmodel import Session, select

from app.db import engine
from app.models import ForwardJob, MessageMap, _now_naive
from app.queue import MAP_RETENTION, Worker, prune_message_map


def _clear():
    with Session(engine) as s:
        for j in s.exec(select(ForwardJob)).all():
            s.delete(j)
        for m in s.exec(select(MessageMap)).all():
            s.delete(m)
        s.commit()


def _insert(bot_id, dest, origin_chat, origin_msg, reply_to=None, quote=None, kind="copy"):
    with Session(engine) as s:
        job = ForwardJob(
            bot_id=bot_id, dest_chat_id=dest, kind=kind,
            from_chat_id=origin_chat, message_id=origin_msg, text="hi",
            origin_chat_id=origin_chat, origin_message_id=origin_msg,
            reply_to_source_message_id=reply_to, reply_quote=quote,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def _pending():
    with Session(engine) as s:
        return len(s.exec(select(ForwardJob).where(ForwardJob.status == "pending")).all())


class IdSender:
    """Returns incrementing dest message ids; records each job dict received."""

    def __init__(self):
        self.jobs: list[dict] = []
        self._next = 1000

    async def __call__(self, job: dict) -> int:
        self.jobs.append(dict(job))
        self._next += 1
        return self._next


async def _drain(send_fn, max_ticks=300):
    worker = Worker(engine, send_fn=send_fn, poll_interval=0.02)
    task = asyncio.create_task(worker.run())
    try:
        for _ in range(max_ticks):
            await asyncio.sleep(0.02)
            if _pending() == 0:
                break
    finally:
        worker.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def _maps(bot_id):
    with Session(engine) as s:
        return s.exec(select(MessageMap).where(MessageMap.bot_id == bot_id)).all()


def test_delivery_captures_message_map():
    _clear()
    _insert(1, dest=20, origin_chat=10, origin_msg=100)
    asyncio.run(_drain(IdSender()))
    rows = _maps(1)
    assert len(rows) == 1
    r = rows[0]
    assert (r.dest_chat_id, r.source_chat_id, r.source_message_id) == (20, 10, 100)
    assert r.dest_message_id > 0


def test_reply_resolves_to_original_dest_message():
    _clear()
    # original (msg 100) then a reply to it (msg 101) -> same dest, id order
    _insert(1, dest=20, origin_chat=10, origin_msg=100)
    _insert(1, dest=20, origin_chat=10, origin_msg=101, reply_to=100, quote="↳ Bob: orig")
    sender = IdSender()
    asyncio.run(_drain(sender))
    # original delivered first -> mapped; reply's send got reply_to_message_id = that dest id
    with Session(engine) as s:
        orig_map = s.exec(
            select(MessageMap).where(
                MessageMap.source_chat_id == 10, MessageMap.source_message_id == 100)
        ).first()
    reply_job = sender.jobs[1]
    assert reply_job["reply_to_message_id"] == orig_map.dest_message_id


def test_reply_without_map_uses_quote_fallback():
    _clear()
    # reply to a message that was never forwarded -> no map -> quote fallback
    _insert(1, dest=20, origin_chat=10, origin_msg=200, reply_to=999, quote="↳ X: gone")
    sender = IdSender()
    asyncio.run(_drain(sender))
    job = sender.jobs[0]
    assert job["reply_to_message_id"] is None and job["reply_quote"] == "↳ X: gone"


def test_prune_removes_old_map_rows():
    _clear()
    now = _now_naive()
    with Session(engine) as s:
        s.add(MessageMap(bot_id=1, dest_chat_id=20, source_chat_id=10,
                         source_message_id=1, dest_message_id=500,
                         created_at=now - MAP_RETENTION - timedelta(hours=1)))  # old
        s.add(MessageMap(bot_id=1, dest_chat_id=20, source_chat_id=10,
                         source_message_id=2, dest_message_id=501,
                         created_at=now))                                       # new
        s.commit()
    removed = prune_message_map(engine)
    assert removed == 1
    left = _maps(1)
    assert len(left) == 1 and left[0].source_message_id == 2
