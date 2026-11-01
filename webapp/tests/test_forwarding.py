"""Pure forwarding-decision + job-building logic (no mocks, no network)."""

import json

from app.forwarding import (
    build_jobs,
    build_quote,
    classify_message,
    decide_action,
    is_sender_allowed,
    is_valid_label,
    is_valid_username,
    normalize_username,
    prefix_len16,
    sanitize_label,
    select_destinations,
    shift_entities,
)
from app.models import Route


def _lmsg(chat, uid, username, message_id=7, **extra):
    m = {"chat": {"id": chat}, "from": {"id": uid, "username": username},
         "message_id": message_id}
    m.update(extra)
    return {"message": m}


def _route(source, dest, enabled=True, source_thread=None, dest_thread=None):
    return Route(bot_id=1, source_chat_id=source, dest_chat_id=dest, enabled=enabled,
                 source_thread_id=source_thread, dest_thread_id=dest_thread)


def _msg(chat_id, from_id, message_id=7, text="hi", username=None):
    frm = {"id": from_id}
    if username is not None:
        frm["username"] = username
    return {"message": {"chat": {"id": chat_id}, "from": frm,
                        "message_id": message_id, "text": text}}


def test_select_destinations_filters_by_source_and_enabled():
    routes = [
        _route(10, 20),
        _route(10, 30),
        _route(99, 40),            # different source
        _route(10, 50, enabled=False),  # disabled
    ]
    assert select_destinations(routes, 10) == [(20, None), (30, None)]


# --- forum topic routing ---

def test_topic_id_requires_is_topic_message():
    from app.forwarding import topic_id
    assert topic_id({"message_thread_id": 7, "is_topic_message": True}) == 7
    assert topic_id({"message_thread_id": 7}) is None          # reply-thread, not a topic
    assert topic_id({}) is None


def test_select_destinations_topic_matching():
    routes = [
        _route(10, 20, source_thread=7, dest_thread=3),   # topic 7 -> dest topic 3
        _route(10, 21),                                   # whole group (any topic)
        _route(10, 22, source_thread=9),                  # topic 9 only
    ]
    # a message in topic 7 -> topic route (20,3) + whole-group route (21,None)
    assert select_destinations(routes, 10, 7) == [(20, 3), (21, None)]
    # topic 9 -> topic-9 route + whole-group
    assert select_destinations(routes, 10, 9) == [(21, None), (22, None)]
    # General / no topic -> only the whole-group route
    assert select_destinations(routes, 10, None) == [(21, None)]


def test_forum_service_message_is_skipped():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 5},
                       "message_id": 7, "forum_topic_created": {"name": "X"}}}
    assert build_jobs(upd, 999, [_route(10, 20)], 1) == []


def test_build_jobs_stamps_dest_thread_id():
    upd = _lmsg(10, 5, "alice", text="hi", is_topic_message=True, message_thread_id=7)
    jobs = build_jobs(upd, 999, [_route(10, 20, source_thread=7, dest_thread=3)], 1)
    assert len(jobs) == 1 and jobs[0].dest_chat_id == 20 and jobs[0].dest_thread_id == 3


def test_build_jobs_labeled_stamps_dest_thread_id():
    upd = _lmsg(10, 5, "alice", text="hi", is_topic_message=True, message_thread_id=7)
    jobs = build_jobs(upd, 999, [_route(10, 20, source_thread=7, dest_thread=3)], 1,
                      label="Doby")
    assert jobs[0].kind == "text" and jobs[0].text == "[Doby] hi" and jobs[0].dest_thread_id == 3


# --- reply-aware forwarding (pure) ---

def test_build_quote_clamps_and_strips():
    assert build_quote("Nguyễn", "hello world") == "↳ Nguyễn: hello world"
    assert build_quote(None, "x") == "↳ ?: x"
    assert build_quote("A", "line\nbreak\rhere") == "↳ A: line break here"
    long = build_quote("A", "y" * 200)
    assert long.startswith("↳ A: ") and long.endswith("…") and len(long) < 100
    assert build_quote("A", "") == "↳ A"


def test_decide_action_extracts_reply():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 5}, "message_id": 7, "text": "hi",
                       "reply_to_message": {"message_id": 100, "from": {"first_name": "Bob"},
                                            "text": "original"}}}
    a = decide_action(upd, telegram_bot_id=999)
    assert a.reply_to_source_message_id == 100
    assert a.reply_quote == "↳ Bob: original"


def test_decide_action_non_reply_has_no_reply_fields():
    a = decide_action(_msg(10, 5), telegram_bot_id=999)
    assert a.reply_to_source_message_id is None and a.reply_quote is None


def test_build_jobs_stamps_origin_and_reply():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 5}, "message_id": 7, "text": "hi",
                       "reply_to_message": {"message_id": 100, "from": {"first_name": "Bob"},
                                            "text": "orig"}}}
    jobs = build_jobs(upd, 999, [_route(10, 20), _route(10, 21)], 1)
    assert len(jobs) == 2
    for j in jobs:
        assert j.origin_chat_id == 10 and j.origin_message_id == 7
        assert j.reply_to_source_message_id == 100
        assert j.reply_quote == "↳ Bob: orig"


def test_sanitize_label():
    assert sanitize_label("Nguyễn") == "Nguyễn"            # unicode kept
    assert sanitize_label("a[b]c") == "abc"                # brackets dropped
    assert sanitize_label("line\nbreak") == "linebreak"    # newline dropped
    assert sanitize_label("x" * 50) == "x" * 32            # clamped to 32
    assert sanitize_label("") is None and sanitize_label(None) is None
    assert sanitize_label("[]") is None                    # nothing usable -> None


def test_build_jobs_label_is_sanitized():
    upd = _lmsg(10, 5, "alice", text="hi")
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="N[a]me")
    assert jobs[0].kind == "text" and jobs[0].text == "[Name] hi"


def test_chatid_in_topic_replies_into_topic():
    upd = _lmsg(10, 5, "alice", text="/chatid", is_topic_message=True, message_thread_id=7)
    jobs = build_jobs(upd, 999, [], 1)
    assert len(jobs) == 1 and jobs[0].dest_thread_id == 7
    assert "chat_id: 10" in jobs[0].text and "message_thread_id (topic): 7" in jobs[0].text


def test_decide_forward_extracts_source_and_message_id():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 5}, "message_id": 7, "text": "hi"}}
    a = decide_action(upd, telegram_bot_id=999)
    assert a.kind == "forward"
    assert a.source_chat_id == 10
    assert a.message_id == 7


def test_loop_guard_skips_bots_own_message():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 999}, "message_id": 7, "text": "hi"}}
    assert decide_action(upd, telegram_bot_id=999).kind == "skip"


def test_chatid_command_from_human():
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 5}, "message_id": 7, "text": "/chatid"}}
    assert decide_action(upd, telegram_bot_id=999).kind == "chatid"


def test_loop_guard_runs_before_command_check():
    # A copied "/chatid" that the bot itself re-received must be skipped,
    # never answered (otherwise it would loop / spam).
    upd = {"message": {"chat": {"id": 10}, "from": {"id": 999}, "message_id": 7, "text": "/chatid"}}
    assert decide_action(upd, telegram_bot_id=999).kind == "skip"


def test_update_without_message_is_skipped():
    assert decide_action({}, telegram_bot_id=999).kind == "skip"


def test_edited_message_is_handled():
    upd = {"edited_message": {"chat": {"id": 10}, "from": {"id": 5}, "message_id": 7, "text": "x"}}
    assert decide_action(upd, telegram_bot_id=999).kind == "forward"


# --- build_jobs (outbox) ---

def test_build_jobs_forward_creates_copy_job_per_dest_in_order():
    routes = [_route(10, 20), _route(10, 30)]
    jobs = build_jobs(_msg(10, 5), telegram_bot_id=999, routes=routes, bot_id=1)
    assert [(j.kind, j.dest_chat_id) for j in jobs] == [("copy", 20), ("copy", 30)]
    assert all(j.from_chat_id == 10 and j.message_id == 7 for j in jobs)


def test_build_jobs_skips_bot_own_message():
    jobs = build_jobs(_msg(10, 999), telegram_bot_id=999, routes=[_route(10, 20)], bot_id=1)
    assert jobs == []


def test_build_jobs_chatid_makes_text_job_to_same_chat():
    jobs = build_jobs(_msg(10, 5, text="/chatid"), telegram_bot_id=999, routes=[], bot_id=1)
    assert len(jobs) == 1
    assert jobs[0].kind == "text" and jobs[0].dest_chat_id == 10
    assert "10" in jobs[0].text


def test_build_jobs_no_route_no_jobs():
    jobs = build_jobs(_msg(10, 5), telegram_bot_id=999, routes=[_route(99, 20)], bot_id=1)
    assert jobs == []


# --- username normalization / validation ---

def test_normalize_username_strips_at_and_lowercases():
    assert normalize_username("@Alice") == "alice"
    assert normalize_username("  BOB_1 ") == "bob_1"


def test_is_valid_username():
    assert is_valid_username("@Alice")        # 5 chars after strip
    assert is_valid_username("bob_12")
    assert not is_valid_username("abc")        # too short
    assert not is_valid_username("has space")
    assert not is_valid_username("bad-dash")


# --- is_sender_allowed (pure whitelist) ---

def test_allowed_empty_list_allows_everyone():
    assert is_sender_allowed("alice", set()) is True
    assert is_sender_allowed(None, set()) is True


def test_allowed_matches_listed_username():
    assert is_sender_allowed("alice", {"alice"}) is True
    assert is_sender_allowed("bob", {"alice"}) is False


def test_allowed_blocks_missing_username_when_list_set():
    assert is_sender_allowed(None, {"alice"}) is False


# --- build_jobs with per-group sender assignment gating ---

def test_build_jobs_gate_inactive_forwards_everyone():
    # gate_active False (bot has no senders) -> forward all, no username needed.
    routes = [_route(10, 20)]
    assert len(build_jobs(_msg(10, 5, username="bob"), 999, routes, 1)) == 1
    assert len(build_jobs(_msg(10, 5), 999, routes, 1, gate_active=True)) == 1  # open group


def test_build_jobs_restricted_group_only_forwards_assigned():
    routes = [_route(10, 20)]
    abs_ = {10: {"alice": None}}  # group 10 restricted to alice
    jobs = build_jobs(_msg(10, 5, username="Alice"), 999, routes, 1, abs_, gate_active=True)
    assert [j.dest_chat_id for j in jobs] == [20]
    assert build_jobs(_msg(10, 5, username="bob"), 999, routes, 1, abs_, gate_active=True) == []
    # no username in a restricted group -> blocked
    assert build_jobs(_msg(10, 5), 999, routes, 1, abs_, gate_active=True) == []


def test_build_jobs_open_group_forwards_everyone_even_when_gate_active():
    # gate_active True but group 11 absent from the map -> open (forward all).
    routes = [_route(10, 20), _route(11, 20)]
    abs_ = {10: {"alice": None}}  # only group 10 restricted
    assert len(build_jobs(_msg(11, 5, username="bob"), 999, routes, 1, abs_, gate_active=True)) == 1


def test_build_jobs_label_applies_in_open_group():
    # Sender labeled globally; posts from an open group -> still gets '[label]'.
    routes = [_route(11, 20)]
    upd = _lmsg(11, 5, "alice", text="hi")
    jobs = build_jobs(
        upd, 999, routes, 1,
        allowed_by_source={10: {"bob": None}},  # group 11 is open
        label="Doby", gate_active=True,
    )
    assert len(jobs) == 1 and jobs[0].kind == "text" and jobs[0].text == "[Doby] hi"


def test_build_jobs_label_applies_in_restricted_group():
    routes = [_route(10, 20)]
    upd = _lmsg(10, 5, "alice", text="hi")
    jobs = build_jobs(
        upd, 999, routes, 1,
        allowed_by_source={10: {"alice": "Doby"}},
        label="Doby", gate_active=True,
    )
    assert jobs[0].kind == "text" and jobs[0].text == "[Doby] hi"


# --- display labels ---

def test_is_valid_label():
    assert is_valid_label("Doby")
    assert is_valid_label("Anh Tu 1")
    assert not is_valid_label("")
    assert not is_valid_label("x" * 33)
    assert not is_valid_label("a[b]")
    assert not is_valid_label("line\nbreak")


def test_prefix_len16_counts_utf16_units():
    assert prefix_len16("[Doby] ") == 7      # ASCII
    assert prefix_len16("\U0001F600") == 2   # emoji = 2 UTF-16 units


def test_shift_entities_offsets_and_no_mutation():
    ents = [{"type": "bold", "offset": 0, "length": 2},
            {"type": "italic", "offset": 5, "length": 3}]
    out = shift_entities(ents, 7)
    assert [(e["offset"], e["length"]) for e in out] == [(7, 2), (12, 3)]
    assert ents[0]["offset"] == 0  # original untouched


def test_classify_message():
    assert classify_message({"text": "hi"}) == "text"
    assert classify_message({"photo": [{}], "caption": "c"}) == "caption_media"
    assert classify_message({"sticker": {}}) == "other"


def test_labeled_text_prefixes_and_shifts_entities():
    upd = _lmsg(10, 5, "alice", text="hi",
                entities=[{"type": "bold", "offset": 0, "length": 2}])
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="Doby")
    assert len(jobs) == 1 and jobs[0].kind == "text"
    assert jobs[0].text == "[Doby] hi"
    ents = json.loads(jobs[0].entities_json)
    assert ents[0]["offset"] == 7 and ents[0]["length"] == 2


def test_labeled_caption_media_overrides_caption():
    upd = _lmsg(10, 5, "alice", photo=[{"file_id": "x"}], caption="pic",
                caption_entities=[{"type": "italic", "offset": 0, "length": 3}])
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="Doby")
    assert len(jobs) == 1 and jobs[0].kind == "copy_caption"
    assert jobs[0].caption == "[Doby] pic"
    assert json.loads(jobs[0].caption_entities_json)[0]["offset"] == 7


def test_labeled_media_without_caption_uses_label_only():
    upd = _lmsg(10, 5, "alice", photo=[{"file_id": "x"}])
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="Doby")
    assert jobs[0].kind == "copy_caption" and jobs[0].caption == "[Doby]"


def test_labeled_other_type_label_line_then_copy_in_order():
    upd = _lmsg(10, 5, "alice", sticker={"file_id": "s"})
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="Doby")
    assert [j.kind for j in jobs] == ["text", "copy"]
    assert jobs[0].text == "[Doby]"


def test_allowed_without_label_is_plain_copy():
    upd = _lmsg(10, 5, "alice", text="hi")
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label=None)
    assert len(jobs) == 1 and jobs[0].kind == "copy" and jobs[0].entities_json is None


def test_labeled_text_over_limit_falls_back_to_plain_copy():
    upd = _lmsg(10, 5, "alice", text="x" * 4096)  # + prefix exceeds 4096
    jobs = build_jobs(upd, 999, [_route(10, 20)], 1, label="Doby")
    assert jobs[0].kind == "copy"  # delivered unlabeled, not dropped
