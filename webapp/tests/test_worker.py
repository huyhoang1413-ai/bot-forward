"""Worker ordering + retry against a real SQLite DB.

No mocks/patching: the network boundary is a real injected async callable
(dependency injection) that records delivery order and can simulate a 429.
This verifies the two guarantees the design promises: no message loss, and
strict per-destination ordering (a retrying head never lets later messages
overtake it).
"""

from __future__ import annotations

import asyncio

from sqlmodel import Session, select

from app.db import engine
from app.models import ForwardJob
from app.queue import Worker


def _clear_jobs():
    with Session(engine) as s:
        for j in s.exec(select(ForwardJob)).all():
            s.delete(j)
        s.commit()


def _insert(dest_chat_id: int, message_id: int) -> int:
    with Session(engine) as s:
        job = ForwardJob(
            bot_id=1, dest_chat_id=dest_chat_id, kind="copy",
            from_chat_id=dest_chat_id, message_id=message_id,
        )
        s.add(job)
        s.commit()
        s.refresh(job)
        return job.id


def _pending_count() -> int:
    with Session(engine) as s:
        return len(s.exec(select(ForwardJob).where(ForwardJob.status == "pending")).all())


class Recorder:
    """Injected sender: records delivered job ids; can fail one id once."""

    def __init__(self, fail_once_id: int | None = None, retry_after: float = 0.05):
        self.calls: list[int] = []
        self._fail_once_id = fail_once_id
        self._retry_after = retry_after
        self._already_failed: set[int] = set()

    async def __call__(self, job: dict) -> None:
        jid = job["id"]
        if jid == self._fail_once_id and jid not in self._already_failed:
            self._already_failed.add(jid)
            err = RuntimeError("simulated 429")
            err.retry_after = self._retry_after  # type: ignore[attr-defined]
            raise err
        self.calls.append(jid)


async def _drain(send_fn, max_ticks: int = 300) -> None:
    worker = Worker(engine, send_fn=send_fn, poll_interval=0.02)
    task = asyncio.create_task(worker.run())
    try:
        for _ in range(max_ticks):
            await asyncio.sleep(0.02)
            if _pending_count() == 0:
                break
    finally:
        worker.stop()
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass


def test_single_chat_delivers_in_id_order():
    _clear_jobs()
    ids = [_insert(3001, i) for i in range(3)]
    rec = Recorder()
    asyncio.run(_drain(rec))
    assert rec.calls == ids           # strict order
    assert _pending_count() == 0      # all delivered (deleted)


def test_retrying_head_is_not_overtaken():
    _clear_jobs()
    first = _insert(3002, 0)
    second = _insert(3002, 1)
    rec = Recorder(fail_once_id=first)  # first job fails once, then succeeds
    asyncio.run(_drain(rec))
    # Despite the retry on `first`, `second` must NOT arrive before it.
    assert rec.calls == [first, second]
    assert _pending_count() == 0


class _PermError(Exception):
    permanent = True


class PermRecorder:
    """Fails one job id with a permanent error; records the rest."""

    def __init__(self, perm_id: int):
        self.calls: list[int] = []
        self._perm_id = perm_id

    async def __call__(self, job: dict) -> None:
        if job["id"] == self._perm_id:
            raise _PermError("message can't be copied")
        self.calls.append(job["id"])


def test_permanent_error_fails_fast_without_blocking_next():
    _clear_jobs()
    bad = _insert(3005, 0)   # will hit a permanent error
    good = _insert(3005, 1)  # must still be delivered after `bad` is failed
    rec = PermRecorder(perm_id=bad)
    asyncio.run(_drain(rec))
    assert rec.calls == [good]         # next message delivered, not blocked
    assert _pending_count() == 0       # nothing stuck pending
    # `bad` is marked failed (kept for inspection), not retried forever
    with Session(engine) as s:
        row = s.get(ForwardJob, bad)
        assert row is not None and row.status == "failed" and row.attempts == 1


def test_different_chats_run_but_keep_per_chat_order():
    _clear_jobs()
    a1 = _insert(3003, 0)
    _b1 = _insert(3004, 0)
    a2 = _insert(3003, 1)
    rec = Recorder()
    asyncio.run(_drain(rec))
    assert set(rec.calls) == {a1, _b1, a2}          # all delivered
    assert rec.calls.index(a1) < rec.calls.index(a2)  # per-chat order preserved
    assert _pending_count() == 0
