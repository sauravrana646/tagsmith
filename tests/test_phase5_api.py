"""Phase 5 API + token crypto tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tagsmith.api.app import create_app
from tagsmith.config import Settings
from tagsmith.db.session import init_db, reset_engine
from tagsmith.security.crypto import decrypt_secret, encrypt_secret


def test_token_crypto_roundtrip() -> None:
    secret = "test-encryption-passphrase"
    token = "refresh-token-abc"
    cipher = encrypt_secret(token, secret_key=secret)
    assert cipher != token
    assert decrypt_secret(cipher, secret_key=secret) == token


def test_api_health_and_plans(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    reset_engine()
    init_db(settings)

    from tagsmith import config as config_mod

    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)

    app = create_app()
    client = TestClient(app)
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["status"] == "ok"

    plans = client.get("/api/billing/plans")
    assert plans.status_code == 200
    assert any(p["id"] == "free" for p in plans.json())

    status = client.get("/api/status")
    assert status.status_code == 200
    assert "gmail_authenticated" in status.json()

    labels = client.get("/api/taxonomy/labels")
    assert labels.status_code == 200
    assert len(labels.json()) >= 16

    summary = client.get("/api/review/summary")
    assert summary.status_code == 200
    assert set(summary.json()) >= {"held", "needs_review", "proposals"}
