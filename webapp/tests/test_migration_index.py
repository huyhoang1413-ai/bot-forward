"""The additive search index migration (real DB, no mocks)."""

from sqlalchemy import inspect

from app.db import _add_search_indexes, create_db_and_tables, engine


def test_search_index_present_and_idempotent():
    create_db_and_tables()
    _add_search_indexes()  # re-run must not error (IF NOT EXISTS)
    names = {i["name"] for i in inspect(engine).get_indexes("allowedsender")}
    assert "ix_allowedsender_bot_username" in names
