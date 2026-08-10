"""Engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from tagsmith.config import Settings

_engine: Engine | None = None


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


def init_db(settings: Settings | None = None) -> Engine:
    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    return engine


def reset_engine() -> None:
    global _engine
    _engine = None


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session
