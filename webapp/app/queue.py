"""Durable outbox worker: deliver ForwardJobs with per-dest ordering + retry.

Guarantees:
- **No loss**: a job stays `pending` (retried with backoff) until delivered, or
  is marked `failed` only after MAX_ATTEMPTS (undeliverable — e.g. bot removed).
- **In order**: for each destination chat, jobs are processed strictly in id
  order, one at a time (a blocked/retrying head holds back later messages to the
  SAME chat). Different chats run concurrently.

Pacing (30/s overall, 20/min per group) + 429 retries are handled by the
AIORateLimiter on the ExtBot in `botcache` — the injected `send_fn`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import timedelta

from sqlalchemy import text
from sqlmodel import Session, select

from app.models import ForwardJob, MessageMap, _now_naive

logger = logging.getLogger(__name__)

MAX_ATTEMPTS = 8
MAP_RETENTION = timedelta(days=3)       # keep reply mappings this long
MAP_PRUNE_EVERY = timedelta(minutes=30)  # how often the worker prunes


def prune_message_map(engine) -> int:
    """Delete MessageMap rows older than the retention window. Returns row count.

    Uses raw SQL with a string cutoff matching SQLite's stored datetime format
    ("YYYY-MM-DD HH:MM:SS.ffffff") so it works regardless of the SQLModel/pydantic
    version's naive-vs-aware datetime strictness on typed ORM comparisons.
    """
    cutoff = (_now_naive() - MAP_RETENTION).strftime("%Y-%m-%d %H:%M:%S.%f")
    with Session(engine) as s:
        result = s.execute(
            text("DELETE FROM messagemap WHERE created_at < :cutoff"),
            {"cutoff": cutoff},
        )
        s.commit()
        return result.rowcount or 0

# send_fn receives a plain dict of job fields and raises on failure.
SendFn = Callable[[dict], Awaitable[None]]


# --------------------------- pure helpers (tested) ---------------------------

def backoff_seconds(attempts: int) -> float:
    """Exponential backoff, capped at 60s: 2, 4, 8, ... , 60."""
    return float(min(60, 2**attempts))


def plan_retry(attempts: int, retry_after: float | None = None) -> tuple[str, int, float]:
    """Decide the next state after a failed send.

    Returns (status, new_attempts, delay_seconds). After MAX_ATTEMPTS the job is
    marked "failed" (undeliverable). If Telegram gave a retry_after, honor it.
    """
    new_attempts = attempts + 1
    if new_attempts >= MAX_ATTEMPTS:
        return "failed", new_attempts, 0.0
    delay = retry_after if retry_after is not None else backoff_seconds(new_attempts)
    return "pending", new_attempts, delay


def _job_to_dict(job: ForwardJob) -> dict:
    return {
        "id": job.id,
        "bot_id": job.bot_id,
        "dest_chat_id": job.dest_chat_id,
        "dest_thread_id": job.dest_thread_id,
        "kind": job.kind,
        "from_chat_id": job.from_chat_id,
        "message_id": job.message_id,
        "text": job.text,
        "entities_json": job.entities_json,
        "caption": job.caption,
        "caption_entities_json": job.caption_entities_json,
        "origin_chat_id": job.origin_chat_id,
        "origin_message_id": job.origin_message_id,
        "reply_to_source_message_id": job.reply_to_source_message_id,
        "reply_quote": job.reply_quote,
        "attempts": job.attempts,
    }


def _lookup_map(
    session, bot_id: int, dest_chat_id: int, source_chat_id: int, source_message_id: int
) -> int | None:
    """Dest message id previously delivered for a source message (for replies)."""
    row = session.exec(
        select(MessageMap)
        .where(
            MessageMap.bot_id == bot_id,
            MessageMap.dest_chat_id == dest_chat_id,
            MessageMap.source_chat_id == source_chat_id,
            MessageMap.source_message_id == source_message_id,
        )
        .order_by(MessageMap.id.desc())
        .limit(1)
    ).first()
    return row.dest_message_id if row else None


# ------------------------------- the worker ---------------------------------

class Worker:
    def __init__(self, engine, send_fn: SendFn, poll_interval: float = 0.5) -> None:
        self._engine = engine
        self._send_fn = send_fn
        self._poll = poll_interval
        self._running = False
        self._tasks: dict[int, asyncio.Task] = {}
        self._last_prune = None

    def stop(self) -> None:
        self._running = False

    async def run(self) -> None:
        """Dispatcher: ensure one per-chat task exists for every chat with work."""
        self._running = True
        while self._running:
            self._maybe_prune()
            for chat in self._chats_with_pending():
                task = self._tasks.get(chat)
                if task is None or task.done():
                    self._tasks[chat] = asyncio.create_task(self._process_chat(chat))
            await asyncio.sleep(self._poll)

    def _maybe_prune(self) -> None:
        now = _now_naive()
        if self._last_prune is not None and now - self._last_prune < MAP_PRUNE_EVERY:
            return
        self._last_prune = now
        try:
            prune_message_map(self._engine)
        except Exception as exc:  # pruning must never break delivery
            logger.warning("message_map prune failed: %s", exc)

    def _chats_with_pending(self) -> list[int]:
        with Session(self._engine) as s:
            rows = s.exec(
                select(ForwardJob.dest_chat_id)
                .where(ForwardJob.status == "pending")
                .distinct()
            ).all()
        return list(rows)

    def _head(self, chat: int) -> dict | None:
        """Oldest pending job for a chat (the only one allowed to send next)."""
        with Session(self._engine) as s:
            job = s.exec(
                select(ForwardJob)
                .where(ForwardJob.dest_chat_id == chat, ForwardJob.status == "pending")
                .order_by(ForwardJob.id)
                .limit(1)
            ).first()
            if job is None:
                return None
            data = _job_to_dict(job)
            data["next_attempt_at"] = job.next_attempt_at
            # Resolve the reply target NOW (send time): the original's job (smaller
            # id, same dest) was delivered + mapped before this one -> correct.
            data["reply_to_message_id"] = None
            if job.reply_to_source_message_id and job.origin_chat_id is not None:
                data["reply_to_message_id"] = _lookup_map(
                    s, job.bot_id, job.dest_chat_id,
                    job.origin_chat_id, job.reply_to_source_message_id,
                )
            return data

    async def _process_chat(self, chat: int) -> None:
        try:
            while self._running:
                head = self._head(chat)
                if head is None:
                    return  # chat drained; dispatcher respawns on new work

                wait = (head["next_attempt_at"] - _now_naive()).total_seconds()
                if wait > 0:
                    # Head not due yet (retry backoff) -> hold the chat, preserve order.
                    await asyncio.sleep(min(wait, 3.0))
                    continue

                try:
                    dest_msg_id = await self._send_fn(head)
                    self._finish(head, dest_msg_id)
                except Exception as exc:  # reschedule or fail; never silently drop
                    if getattr(exc, "permanent", False):
                        # Undeliverable (e.g. "message can't be copied", bot kicked)
                        # -> fail fast so it does NOT block later messages to this chat.
                        self._reschedule(
                            head["id"], "failed", head["attempts"] + 1, 0.0, str(exc)
                        )
                        logger.error(
                            "job %s to chat %s permanently failed: %s",
                            head["id"], chat, exc,
                        )
                    else:
                        retry_after = getattr(exc, "retry_after", None)
                        status, attempts, delay = plan_retry(
                            head["attempts"], _as_float(retry_after)
                        )
                        self._reschedule(head["id"], status, attempts, delay, str(exc))
                        if status == "failed":
                            logger.error(
                                "job %s to chat %s FAILED after %s attempts: %s",
                                head["id"], chat, attempts, exc,
                            )
        finally:
            self._tasks.pop(chat, None)

    def _finish(self, head: dict, dest_msg_id: int | None) -> None:
        """After a successful send: record the source->dest map and delete the job
        in one transaction. A crash before commit -> job stays pending -> redeliver
        (at-least-once, unchanged). A map insert without delete never happens."""
        with Session(self._engine) as s:
            if dest_msg_id and head.get("origin_message_id") is not None:
                s.add(MessageMap(
                    bot_id=head["bot_id"],
                    dest_chat_id=head["dest_chat_id"],
                    source_chat_id=head["origin_chat_id"],
                    source_message_id=head["origin_message_id"],
                    dest_message_id=dest_msg_id,
                ))
            job = s.get(ForwardJob, head["id"])
            if job:
                s.delete(job)
            s.commit()

    def _reschedule(
        self, job_id: int, status: str, attempts: int, delay: float, error: str
    ) -> None:
        with Session(self._engine) as s:
            job = s.get(ForwardJob, job_id)
            if not job:
                return
            job.status = status
            job.attempts = attempts
            job.last_error = error[:300]
            job.next_attempt_at = _now_naive() + timedelta(seconds=delay)
            s.add(job)
            s.commit()


def _as_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
