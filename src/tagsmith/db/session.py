"""Engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from tagsmith.config import Settings

_engine: Engine | None = None

# Lightweight SQLite column adds for already-created local DBs.
_SQLITE_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("classifications", "proposed_key", "TEXT"),
    ("classifications", "proposed_description", "TEXT"),
    ("classifications", "proposed_why", "TEXT"),
]


def get_engine(settings: Settings | None = None, *, echo: bool = False) -> Engine:
    global _engine
    if _engine is not None and settings is None:
        return _engine
    if settings is None:
        from tagsmith.config import get_settings

        settings = get_settings()
    url = settings.database_url
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    engine = create_engine(url, echo=echo, connect_args=connect_args)
    if settings is None or _engine is None:
        _engine = engine
    return engine


def _migrate_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        for table, column, col_type in _SQLITE_COLUMN_MIGRATIONS:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {row[1] for row in rows}
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))


def init_db(settings: Settings | None = None) -> Engine:
    # Ensure Phase 3 RAG table is registered on SQLModel.metadata.
    from tagsmith.rag.store import RagExample  # noqa: F401

    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite(engine)
    return engine


def reset_engine() -> None:
    global _engine
    _engine = None


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session
