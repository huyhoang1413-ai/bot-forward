"""Database engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import event, inspect
from sqlmodel import Session, SQLModel, create_engine

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


def get_session() -> Iterator[Session]:
    with Session(engine) as session:
        yield session
