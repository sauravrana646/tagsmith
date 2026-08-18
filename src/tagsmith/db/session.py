"""Engine and session helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlmodel import Session, SQLModel, create_engine

from tagsmith.config import Settings

_engine: Engine | None = None

LOCAL_TENANT_ID = 1
LOCAL_TENANT_EMAIL = "local@tagsmith.invalid"

# Lightweight SQLite column adds for already-created local DBs.
_SQLITE_COLUMN_MIGRATIONS: list[tuple[str, str, str]] = [
    ("classifications", "proposed_key", "TEXT"),
    ("classifications", "proposed_description", "TEXT"),
    ("classifications", "proposed_why", "TEXT"),
    ("classifications", "tenant_id", "INTEGER DEFAULT 1"),
    ("tenants", "display_name", "TEXT"),
    ("tenants", "picture_url", "TEXT"),
    ("tenants", "stripe_customer_id", "TEXT"),
    ("sync_state", "last_rag_catchup_at", "TIMESTAMP"),
    ("sync_state", "last_rag_indexed", "INTEGER"),
    ("sync_state", "last_rag_removed", "INTEGER"),
    ("sync_state", "tenant_id", "INTEGER DEFAULT 1"),
    ("messages", "tenant_id", "INTEGER DEFAULT 1"),
    ("proposals", "tenant_id", "INTEGER DEFAULT 1"),
    ("runs", "tenant_id", "INTEGER DEFAULT 1"),
    ("negative_examples", "tenant_id", "INTEGER DEFAULT 1"),
    ("categories", "tenant_id", "INTEGER DEFAULT 1"),
    ("rag_examples", "tenant_id", "INTEGER DEFAULT 1"),
]


def get_engine(settings: Settings | None = None, *, echo: bool = False) -> Engine:
    global _engine
    if settings is None:
        if _engine is not None:
            return _engine
        from tagsmith.config import get_settings

        settings = get_settings()

    url = settings.database_url
    if _engine is not None and str(_engine.url) == url:
        return _engine

    is_sqlite = url.startswith("sqlite")
    connect_args: dict[str, object] = {}
    if is_sqlite:
        connect_args = {"check_same_thread": False, "timeout": 30.0}
    engine = create_engine(url, echo=echo, connect_args=connect_args)
    if is_sqlite:
        _register_sqlite_pragmas(engine)
    _engine = engine
    return engine


def _register_sqlite_pragmas(engine: Engine) -> None:
    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn: object, _connection_record: object) -> None:
        cursor = dbapi_conn.cursor()  # type: ignore[attr-defined]
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.execute("PRAGMA busy_timeout=30000")
        cursor.close()


def _migrate_sqlite(engine: Engine) -> None:
    if engine.dialect.name != "sqlite":
        return
    with engine.begin() as conn:
        for table, column, col_type in _SQLITE_COLUMN_MIGRATIONS:
            rows = conn.execute(text(f"PRAGMA table_info({table})")).fetchall()
            existing = {row[1] for row in rows}
            if not existing:
                continue
            if column not in existing:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {column} {col_type}"))
        conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_proposal_dedupe_pending "
                "ON proposals(dedupe_key) WHERE status = 'pending'"
            )
        )


def _ensure_local_tenant(engine: Engine) -> None:
    from tagsmith.db.models import Tenant

    with Session(engine) as session:
        tenant = session.get(Tenant, LOCAL_TENANT_ID)
        if tenant is None:
            session.add(
                Tenant(
                    id=LOCAL_TENANT_ID,
                    email=LOCAL_TENANT_EMAIL,
                    display_name="Local operator",
                    plan="free",
                )
            )
            session.commit()


def init_db(settings: Settings | None = None) -> Engine:
    # Ensure optional tables are registered on SQLModel.metadata.
    from tagsmith.db import models as _models  # noqa: F401
    from tagsmith.rag.store import RagExample  # noqa: F401

    engine = get_engine(settings)
    SQLModel.metadata.create_all(engine)
    _migrate_sqlite(engine)
    _ensure_local_tenant(engine)
    return engine


def reset_engine() -> None:
    global _engine
    if _engine is not None:
        _engine.dispose()
    _engine = None


@contextmanager
def get_session(settings: Settings | None = None) -> Iterator[Session]:
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session
