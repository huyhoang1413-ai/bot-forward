"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine, select

from app.config import get_settings

# Import models so their tables are registered on SQLModel.metadata.
from app import models  # noqa: F401  (side-effect import)

_url = get_settings().database_url
_connect_args = {}

if _url.startswith("sqlite"):
    _connect_args = {"check_same_thread": False}
    # Ensure the parent directory of a file-based sqlite db exists.
    db_path = _url.split("sqlite:///", 1)[-1]
    if db_path and db_path not in (":memory:",):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)

engine = create_engine(_url, connect_args=_connect_args)

if _url.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _sqlite_pragmas(dbapi_conn, _record):  # noqa: ANN001
        # WAL lets many readers run alongside a writer -> better under webhook load.
        cur = dbapi_conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL")
        cur.execute("PRAGMA synchronous=NORMAL")
        cur.close()


def create_db_and_tables() -> None:
    SQLModel.metadata.create_all(engine)
    _add_missing_columns()
    _add_search_indexes()
    _collapse_allowed_senders_to_global()
    # NOTE: _backfill_group_sender_assignments() is intentionally NOT called.
    # It auto-assigned every nickname-list sender to every source group, which
    # silently turned the (display-only) nickname list into a per-group forward
    # gate -> the "only 1 person forwards" incident. Gating is now explicit per
    # route only ("Người gửi được phép"). Kept as a no-op for history.


def _add_missing_columns() -> None:
    """Lightweight additive migration: ADD COLUMN for any new nullable model
    field missing from an existing table. create_all() alone never alters
    existing tables, so a persistent SQLite DB would otherwise miss new columns.
    """
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in SQLModel.metadata.sorted_tables:
            if not insp.has_table(table.name):
                continue
            existing = {c["name"] for c in insp.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing:
                    continue
                # Can only safely add a column that is nullable or has a default.
                if not col.nullable and col.default is None and col.server_default is None:
                    continue
                ddl_type = col.type.compile(dialect=engine.dialect)
                conn.exec_driver_sql(
                    f'ALTER TABLE "{table.name}" ADD COLUMN "{col.name}" {ddl_type}'
                )


def _collapse_allowed_senders_to_global() -> None:
    """One-time data migration: the allowlist used to be per source group; it is
    now global per bot. Move every AllowedSender row into the GLOBAL_SOURCE (0)
    bucket, deduping by (bot_id, username) and keeping any non-empty label.

    Idempotent: a no-op once every row already lives in the global bucket.
    """
    from app.models import GLOBAL_SOURCE, AllowedSender

    if not inspect(engine).has_table("allowedsender"):
        return
    with Session(engine) as session:
        legacy = session.exec(
            select(AllowedSender).where(AllowedSender.source_chat_id != GLOBAL_SOURCE)
        ).all()
        if not legacy:
            return
        # Global rows already present, keyed by (bot_id, username) to merge into.
        kept: dict[tuple[int, str], AllowedSender] = {
            (r.bot_id, r.username): r
            for r in session.exec(
                select(AllowedSender).where(AllowedSender.source_chat_id == GLOBAL_SOURCE)
            ).all()
        }
        for row in legacy:
            key = (row.bot_id, row.username)
            existing = kept.get(key)
            if existing is None:
                row.source_chat_id = GLOBAL_SOURCE  # promote this row to global
                session.add(row)
                kept[key] = row
            else:
                if existing.label is None and row.label is not None:
                    existing.label = row.label  # keep a label if any duplicate had one
                    session.add(existing)
                session.delete(row)  # drop the now-redundant per-group duplicate
        session.commit()


def _add_search_indexes() -> None:
    """Additive: create a case-insensitive index on (bot_id, username) so the
    admin UI's prefix search (``username LIKE 'q%'``) is index-backed at 500-1000
    senders. ``create_all()`` can't add an index to an existing table, and
    COLLATE NOCASE needs raw DDL. Idempotent via IF NOT EXISTS.
    """
    if not inspect(engine).has_table("allowedsender"):
        return
    with engine.begin() as conn:
        conn.exec_driver_sql(
            "CREATE INDEX IF NOT EXISTS ix_allowedsender_bot_username "
            "ON allowedsender(bot_id, username COLLATE NOCASE)"
        )


def _backfill_group_sender_assignments() -> None:
    """DEPRECATED / no-op. Previously assigned every global sender to every
    source group, which silently turned the display-only nickname list into a
    per-group forward gate (cause of the "only 1 person forwards" incident).
    Gating is now explicit per route only. Left as a no-op so no NEW auto-gates
    are ever created; existing assignment rows are untouched (clean them by
    removing senders from a route's "Người gửi được phép" if unwanted).
    """
    return


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
