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


def test_backfill_assigns_every_sender_to_every_source_group():
    bid = _seed(7101)
    _backfill_group_sender_assignments()
    rows = _assignments(bid)
    # 2 senders x 2 groups = 4 assignments; preserves 'applies to all groups'.
    assert len(rows) == 4
    assert {r.source_chat_id for r in rows} == {100, 101}


def test_backfill_is_idempotent():
    bid = _seed(7102)
    _backfill_group_sender_assignments()
    _backfill_group_sender_assignments()  # second run must not duplicate
    assert len(_assignments(bid)) == 4


def test_backfill_no_routes_no_assignments():
    # Sender exists but bot has no routes -> nothing to assign.
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=7103, username="u",
            token_encrypted=encrypt_token("123:fake"), webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        s.add(AllowedSender(bot_id=bot.id, username="alice"))
        s.commit()
        bid = bot.id
    _backfill_group_sender_assignments()
    assert _assignments(bid) == []
