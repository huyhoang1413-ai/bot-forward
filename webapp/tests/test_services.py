"""Route service logic against a real SQLite DB (no mocks)."""

from sqlmodel import Session, select

from app.crypto import encrypt_token
from app.db import engine
from app.models import AllowedSender, Bot, Route, SenderGroupAssignment
from app.services import (
    add_allowed_sender,
    add_group_sender,
    add_route,
    add_sender_by_username,
    count_senders,
    delete_allowed_sender,
    delete_route,
    group_sender_counts,
    list_group_senders,
    list_senders,
    remove_group_sender,
    search_unassigned,
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


def _allowed(session, bot_id):
    return session.exec(
        select(AllowedSender).where(AllowedSender.bot_id == bot_id)
    ).all()


def test_add_allowed_sender_normalizes_and_dedupes():
    bot_id = _make_bot(2101)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, "@Alice")
        add_allowed_sender(s, bot_id, "alice")  # same after normalize
        rows = _allowed(s, bot_id)
        assert [r.username for r in rows] == ["alice"]


def test_add_allowed_sender_is_global_single_row():
    bot_id = _make_bot(2102)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20, bidirectional=True)  # routes 10->20 and 20->10
        add_allowed_sender(s, bot_id, "alice")
        rows = _allowed(s, bot_id)
        # One global row covers every group of the bot (no per-group duplication).
        assert [r.username for r in rows] == ["alice"]
        assert rows[0].source_chat_id == 0


def test_delete_allowed_sender_scoped_to_bot():
    bot_a = _make_bot(2103)
    bot_b = _make_bot(2104)
    with Session(engine) as s:
        add_allowed_sender(s, bot_a, "alice")
        row = _allowed(s, bot_a)[0]
        delete_allowed_sender(s, row.id, bot_id=bot_b)  # wrong bot -> no-op
        assert len(_allowed(s, bot_a)) == 1
        delete_allowed_sender(s, row.id, bot_id=bot_a)  # correct -> deleted
        assert len(_allowed(s, bot_a)) == 0


def test_add_allowed_sender_with_label():
    bot_id = _make_bot(2201)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, "@Alice", label="Doby")
        rows = _allowed(s, bot_id)
        assert [(r.username, r.label) for r in rows] == [("alice", "Doby")]


def test_add_allowed_sender_updates_label_on_existing():
    bot_id = _make_bot(2202)
    with Session(engine) as s:
        add_allowed_sender(s, bot_id, "alice")            # no label
        add_allowed_sender(s, bot_id, "alice", label="Doby")  # sets label
        rows = _allowed(s, bot_id)
        assert len(rows) == 1 and rows[0].label == "Doby"


def test_update_allowed_label_scoped_and_clears():
    bot_a = _make_bot(2203)
    bot_b = _make_bot(2204)
    with Session(engine) as s:
        add_allowed_sender(s, bot_a, "alice", label="Doby")
        row = _allowed(s, bot_a)[0]
        update_allowed_label(s, row.id, "New", bot_id=bot_b)  # wrong bot -> no-op
        assert _allowed(s, bot_a)[0].label == "Doby"
        update_allowed_label(s, row.id, "New", bot_id=bot_a)
        assert _allowed(s, bot_a)[0].label == "New"
        update_allowed_label(s, row.id, "  ", bot_id=bot_a)   # blank -> clear
        assert _allowed(s, bot_a)[0].label is None


# --- per-group sender assignment ---

def _assigns(session, source_chat_id, sender_ids):
    return session.exec(
        select(SenderGroupAssignment).where(
            SenderGroupAssignment.source_chat_id == source_chat_id,
            SenderGroupAssignment.allowed_sender_id.in_(sender_ids or [-1]),
        )
    ).all()


def test_add_group_sender_idempotent_and_bot_scoped():
    bot_id = _make_bot(2301)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        assert add_group_sender(s, bot_id, 10, a.id) is True
        assert add_group_sender(s, bot_id, 10, a.id) is True  # idempotent, no dup
        assert {x.allowed_sender_id for x in _assigns(s, 10, [a.id])} == {a.id}
        assert len(_assigns(s, 10, [a.id])) == 1


def test_add_group_sender_rejects_non_source_group():
    bot_id = _make_bot(2302)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        assert add_group_sender(s, bot_id, 999, a.id) is False  # 999 not a source
        assert _assigns(s, 999, [a.id]) == []


def test_add_group_sender_rejects_foreign_sender():
    bot_a = _make_bot(2303)
    bot_b = _make_bot(2304)
    with Session(engine) as s:
        add_route(s, bot_a, 10, 20)
        foreign = add_allowed_sender(s, bot_b, "eve")  # belongs to bot_b
        assert add_group_sender(s, bot_a, 10, foreign.id) is False  # IDOR
        assert _assigns(s, 10, [foreign.id]) == []


def test_remove_group_sender():
    bot_id = _make_bot(2307)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        add_group_sender(s, bot_id, 10, a.id)
        remove_group_sender(s, bot_id, 10, a.id)
        assert _assigns(s, 10, [a.id]) == []


def test_delete_allowed_sender_cascades_assignments():
    bot_id = _make_bot(2305)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        add_group_sender(s, bot_id, 10, a.id)
        assert len(_assigns(s, 10, [a.id])) == 1
        delete_allowed_sender(s, a.id, bot_id=bot_id)
        assert _assigns(s, 10, [a.id]) == []


def test_delete_last_route_cleans_group_assignments():
    bot_id = _make_bot(2306)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        add_group_sender(s, bot_id, 10, a.id)
        route = s.exec(
            select(Route).where(Route.bot_id == bot_id, Route.source_chat_id == 10)
        ).first()
        delete_route(s, route.id, bot_id=bot_id)  # last route of source 10
        assert _assigns(s, 10, [a.id]) == []


# --- search / pagination helpers ---

def test_list_senders_search_and_paginate():
    bot_id = _make_bot(2401)
    with Session(engine) as s:
        for i in range(120):
            add_allowed_sender(s, bot_id, f"user{i:03d}")
        add_allowed_sender(s, bot_id, "alice")
        # page 0 default size 50
        items, total = list_senders(s, bot_id)
        assert total == 121 and len(items) == 50
        # page 2 -> remaining 21
        items2, _ = list_senders(s, bot_id, page=2)
        assert len(items2) == 21
        # prefix search
        res, rtotal = list_senders(s, bot_id, q="alic")
        assert rtotal == 1 and res[0].username == "alice"
        # '@' + uppercase normalized
        res2, _ = list_senders(s, bot_id, q="@ALIC")
        assert res2 and res2[0].username == "alice"


def test_search_unassigned_excludes_assigned():
    bot_id = _make_bot(2402)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        a = add_allowed_sender(s, bot_id, "alice")
        b = add_allowed_sender(s, bot_id, "bob")
        add_group_sender(s, bot_id, 10, a.id)
        picker, total = search_unassigned(s, bot_id, 10)
        names = {x.username for x in picker}
        assert names == {"bob"} and total == 1
        # assigned list shows alice
        assigned, atotal = list_group_senders(s, bot_id, 10)
        assert {x.username for x in assigned} == {"alice"} and atotal == 1
        _ = b


def test_add_sender_by_username_creates_and_assigns():
    bot_id = _make_bot(2404)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        # new username -> created in registry + assigned to group
        assert add_sender_by_username(s, bot_id, 10, "@Alice", label="Doby") is True
        senders, total = list_senders(s, bot_id)
        assert total == 1 and senders[0].username == "alice" and senders[0].label == "Doby"
        assigned, atotal = list_group_senders(s, bot_id, 10)
        assert atotal == 1 and assigned[0].username == "alice"
        # same username again -> no duplicate registry row, still assigned
        add_sender_by_username(s, bot_id, 10, "alice")
        _, total2 = list_senders(s, bot_id)
        assert total2 == 1


def test_add_sender_by_username_rejects_non_source():
    bot_id = _make_bot(2405)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        assert add_sender_by_username(s, bot_id, 999, "alice") is False
        assert count_senders(s, bot_id) == 0  # nothing created for a bad source


def test_count_helpers():
    bot_id = _make_bot(2403)
    with Session(engine) as s:
        add_route(s, bot_id, 10, 20)
        add_route(s, bot_id, 11, 21)
        a = add_allowed_sender(s, bot_id, "alice")
        add_allowed_sender(s, bot_id, "bob")
        add_group_sender(s, bot_id, 10, a.id)
        assert count_senders(s, bot_id) == 2
        assert group_sender_counts(s, bot_id) == {10: 1}
