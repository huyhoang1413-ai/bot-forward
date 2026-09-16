"""Webhook receiver: one endpoint multiplexes all bots via {bot_id}.

Fast + durable: verify secret, persist outbox jobs, return 200. The background
worker does the actual sending (rate-limited, ordered, retried). Returning 200
only after the DB commit means a crash before commit -> Telegram redelivers.
"""

from __future__ import annotations

import hmac
import logging

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlmodel import Session, select

from app.db import get_session
from app.forwarding import build_jobs
from app.models import AllowedSender
from app.models import Bot as BotModel
from app.models import Route, SenderGroupAssignment

logger = logging.getLogger(__name__)

router = APIRouter()

_SECRET_HEADER = "X-Telegram-Bot-Api-Secret-Token"


@router.post("/webhook/{bot_id}")
async def receive_update(
    bot_id: int, request: Request, session: Session = Depends(get_session)
):
    bot_row = session.get(BotModel, bot_id)
    if not bot_row or bot_row.status != "active":
        raise HTTPException(status_code=404, detail="Not found")

    provided = request.headers.get(_SECRET_HEADER, "")
    if not hmac.compare_digest(provided, bot_row.webhook_secret):
        raise HTTPException(status_code=403, detail="Bad secret")

    update = await request.json()
    routes = session.exec(select(Route).where(Route.bot_id == bot_id)).all()

    # Single LEFT JOIN: the bot's senders + their per-group assignments in one
    # round-trip (no 1000-id IN-list -> sidesteps SQLite's parameter limit).
    # A source appears in allowed_by_source only if it has ≥1 assignment
    # (absence => 'open' group); never store an empty set for a source.
    label_map: dict[str, str | None] = {}
    allowed_by_source: dict[int, dict[str, str | None]] = {}
    for snd, assign in session.exec(
        select(AllowedSender, SenderGroupAssignment)
        .join(
            SenderGroupAssignment,
            AllowedSender.id == SenderGroupAssignment.allowed_sender_id,
            isouter=True,
        )
        .where(AllowedSender.bot_id == bot_id)
    ).all():
        label_map[snd.username] = snd.label
        if assign is not None:
            allowed_by_source.setdefault(assign.source_chat_id, {})[snd.username] = snd.label
    gate_active = bool(label_map)  # no senders -> forward everyone (legacy)

    jobs = build_jobs(
        update, bot_row.telegram_bot_id, routes, bot_id,
        allowed_by_source, label_map, gate_active,
    )
    for job in jobs:
        session.add(job)
    session.commit()  # durable before we ack -> no inbound loss

    return {"ok": True}
