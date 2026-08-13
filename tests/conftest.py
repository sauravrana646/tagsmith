"""Shared pytest fixtures."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlmodel import Session, SQLModel, create_engine
from tests.fixtures.messages import ALL_FIXTURES

from tagsmith.config import Settings
from tagsmith.db import models as _models  # noqa: F401
from tagsmith.db.session import reset_engine
from tagsmith.gmail.fake import FakeGmail
from tagsmith.rag.store import RagExample  # noqa: F401
from tagsmith.taxonomy.registry import TaxonomyRegistry


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    reset_engine()
    db_path = tmp_path / "test.db"
    return Settings(
        google_client_secret_path=tmp_path / "credentials.json",
        token_path=tmp_path / "token.json",
        database_url=f"sqlite:///{db_path}",
        rules_path=tmp_path / "rules.yaml",
        llm_model="test",
        body_char_limit=2000,
        log_level="WARNING",
        enable_background_sync=False,
    )


@pytest.fixture()
def session(settings: Settings) -> Iterator[Session]:
    reset_engine()
    engine = create_engine(
        settings.database_url,
        connect_args={"check_same_thread": False},
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as sess:
        TaxonomyRegistry(sess, settings).ensure_seeded()
        yield sess
    reset_engine()


@pytest.fixture()
def fake_gmail() -> FakeGmail:
    return FakeGmail(messages=[dict(m) for m in ALL_FIXTURES])
