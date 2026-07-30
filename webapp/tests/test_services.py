"""Route service logic against a real SQLite DB (no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, Route
from app.services import (
    add_allowed_sender,
    add_route,
    delete_allowed_sender,
    delete_route,
    update_allowed_label,
)


def _make_bot(telegram_bot_id: int) -> int:
    with Session(engine) as s:
        bot = Bot(
            telegram_bot_id=telegram_bot_id,
            username="u",
            token_encrypted=encrypt_token("123:fake"),
            webhook_secret="s",
        )
        s.add(bot)
        s.commit()
        s.refresh(bot)
        return bot.id


def _routes(session, bot_id):
    return session.exec(select(Route).where(Route.bot_id == bot_id)).all()


def test_add_route_bidirectional_creates_both_directions():
    bot_id = _make_bot(2001)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20, bidirectional=True)
        pairs = {(r.source_chat_id, r.dest_chat_id) for r in _routes(s, bot_id)}
    assert pairs == {(10, 20), (20, 10)}


def test_add_route_is_deduped():
    bot_id = _make_bot(2002)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        add_route(s, bot_id, 10, 20)  # duplicate
        assert len(_routes(s, bot_id)) == 1


def test_delete_route_scoped_to_bot_blocks_cross_bot():
    bot_a = _make_bot(2003)
    bot_b = _make_bot(2004)
    with Session(engine) as s:
        add_route(s, bot_a, 10, 20)
        route_a = _routes(s, bot_a)[0]
        # Try to delete bot_a's route while claiming bot_b -> must NOT delete.
        delete_route(s, route_a.id, bot_id=bot_b)
        assert len(_routes(s, bot_a)) == 1
        # Correct owner -> deletes.
        delete_route(s, route_a.id, bot_id=bot_a)
        assert len(_routes(s, bot_a)) == 0


def _allowed(session, bot_id, source):
    return session.exec(
        select(AllowedSender).where(
            AllowedSender.bot_id == bot_id, AllowedSender.source_chat_id == source
        )
    ).all()


def test_add_allowed_sender_normalizes_and_dedupes():
    bot_id = _make_bot(2101)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, 10, "@Alice")
        add_allowed_sender(s, bot_id, 10, "alice")  # same after normalize
        rows = _allowed(s, bot_id, 10)
        assert [r.username for r in rows] == ["alice"]


def test_add_allowed_sender_both_ways_covers_bridge_partner():
    bot_id = _make_bot(2102)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20, bidirectional=True)  # routes 10->20 and 20->10
        add_allowed_sender(s, bot_id, 10, "alice", both_ways=True)
        assert [r.username for r in _allowed(s, bot_id, 10)] == ["alice"]
        assert [r.username for r in _allowed(s, bot_id, 20)] == ["alice"]  # partner


def test_delete_allowed_sender_scoped_to_bot():
    bot_a = _make_bot(2103)
    bot_b = _make_bot(2104)
    with Session(engine) as s:
        add_allowed_sender(s, bot_a, 10, "alice")
        row = _allowed(s, bot_a, 10)[0]
        delete_allowed_sender(s, row.id, bot_id=bot_b)  # wrong bot -> no-op
        assert len(_allowed(s, bot_a, 10)) == 1
        delete_allowed_sender(s, row.id, bot_id=bot_a)  # correct -> deleted
        assert len(_allowed(s, bot_a, 10)) == 0


def test_add_allowed_sender_with_label():
    bot_id = _make_bot(2201)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, 10, "@Alice", label="Doby")
        rows = _allowed(s, bot_id, 10)
        assert [(r.username, r.label) for r in rows] == [("alice", "Doby")]


def test_add_allowed_sender_updates_label_on_existing():
    bot_id = _make_bot(2202)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, 10, "alice")            # no label
        add_allowed_sender(s, bot_id, 10, "alice", label="Doby")  # sets label
        rows = _allowed(s, bot_id, 10)
        assert len(rows) == 1 and rows[0].label == "Doby"


def test_both_ways_carries_label_to_partner():
    bot_id = _make_bot(2205)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20, bidirectional=True)
        add_allowed_sender(s, bot_id, 10, "alice", both_ways=True, label="Doby")
        assert _allowed(s, bot_id, 10)[0].label == "Doby"
        assert _allowed(s, bot_id, 20)[0].label == "Doby"


def test_update_allowed_label_scoped_and_clears():
    bot_a = _make_bot(2203)
    bot_b = _make_bot(2204)
    with Session(engine) as s:
        add_allowed_sender(s, bot_a, 10, "alice", label="Doby")
        row = _allowed(s, bot_a, 10)[0]
        update_allowed_label(s, row.id, "New", bot_id=bot_b)  # wrong bot -> no-op
        assert _allowed(s, bot_a, 10)[0].label == "Doby"
        update_allowed_label(s, row.id, "New", bot_id=bot_a)
        assert _allowed(s, bot_a, 10)[0].label == "New"
        update_allowed_label(s, row.id, "  ", bot_id=bot_a)   # blank -> clear
        assert _allowed(s, bot_a, 10)[0].label is None
