"""Backfill migration for per-group sender assignments (real DB, no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import _backfill_group_sender_assignments, engine
from app.models import AllowedSender, Bot, Route, SenderGroupAssignment


def _seed(telegram_bot_id: int) -> int:
    """Bot with 2 global senders and routes into 2 source groups."""
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(Route(bot_id=bot.id, source_chat_id=100, dest_chat_id=200))
        s.add(Route(bot_id=bot.id, source_chat_id=101, dest_chat_id=201))
        s.add(AllowedSender(bot_id=bot.id, username="alice"))
        s.add(AllowedSender(bot_id=bot.id, username="bob"))
        s.commit()
        return bot.id


def _assignments(bot_id: int):
    with Session(engine) as s:
        own = [r.id for r in s.exec(
            select(AllowedSender).where(AllowedSender.bot_id == bot_id)).all()]
        return s.exec(
            select(SenderGroupAssignment).where(
                SenderGroupAssignment.allowed_sender_id.in_(own))
        ).all()


def test_backfill_is_noop_creates_no_gates():
    # DEPRECATED behavior: the migration must NOT auto-assign senders to groups
    # anymore (that silently gated forwarding -> the "only 1 person forwards"
    # incident). Gating is now explicit per route only.
    bid = _seed(7101)
    _backfill_group_sender_assignments()
    assert _assignments(bid) == []


def test_backfill_leaves_existing_assignments_untouched():
    # Any assignments created explicitly (e.g. via the per-route "Người gửi được
    # phép" box) must survive the no-op migration unchanged.
    bid = _seed(7102)
    with Session(engine) as s:
        snd = s.exec(
            select(AllowedSender).where(AllowedSender.bot_id == bid)).first()
        s.add(SenderGroupAssignment(allowed_sender_id=snd.id, source_chat_id=100))
        s.commit()
    _backfill_group_sender_assignments()
    rows = _assignments(bid)
    assert len(rows) == 1 and rows[0].source_chat_id == 100
