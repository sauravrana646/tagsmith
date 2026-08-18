"""Phase 5 API + token crypto tests."""

from __future__ import annotations

from fastapi.testclient import TestClient

from tagsmith.api.app import create_app
from tagsmith.api.auth.session import sign_session_value
from tagsmith.config import Settings
from tagsmith.db.models import Tenant
from tagsmith.db.session import LOCAL_TENANT_ID, init_db, reset_engine
from tagsmith.gmail.fake import FakeGmail
from tagsmith.security.crypto import decrypt_secret, encrypt_secret


def _client(settings: Settings, monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    reset_engine()
    init_db(settings)
    from tagsmith import config as config_mod

    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr("tagsmith.api.app.get_settings", lambda: settings)
    monkeypatch.setattr("tagsmith.api.deps.get_settings", lambda: settings)
    client = TestClient(create_app())
    token = sign_session_value(LOCAL_TENANT_ID, settings.session_signing_key)
    client.cookies.set("tagsmith_tenant", token)
    return client


def _unauth_client(settings: Settings, monkeypatch) -> TestClient:  # type: ignore[no-untyped-def]
    reset_engine()
    init_db(settings)
    from tagsmith import config as config_mod

    monkeypatch.setattr(config_mod, "get_settings", lambda: settings)
    monkeypatch.setattr("tagsmith.api.app.get_settings", lambda: settings)
    monkeypatch.setattr("tagsmith.api.deps.get_settings", lambda: settings)
    return TestClient(create_app())


def test_token_crypto_roundtrip() -> None:
    secret = "test-encryption-passphrase"
    token = "refresh-token-abc"
    cipher = encrypt_secret(token, secret_key=secret)
    assert cipher != token
    assert cipher.startswith("v2:")
    assert decrypt_secret(cipher, secret_key=secret) == token


def test_token_crypto_decrypts_legacy_v1() -> None:
    import base64
    import hashlib

    from cryptography.fernet import Fernet

    secret = "legacy-secret"
    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    legacy = Fernet(base64.urlsafe_b64encode(digest)).encrypt(b"old-token").decode("ascii")
    assert decrypt_secret(legacy, secret_key=secret) == "old-token"


def test_api_health_and_plans(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _client(settings, monkeypatch)
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

    status_body = status.json()
    assert status_body["enable_rag"] is True
    assert isinstance(status_body["rag_example_count"], int)
    assert "background_sync" in status_body
    assert "last_rag_catchup_at" in status_body


def test_api_sync_run_unauthorized(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    res = client.post("/api/sync/run", json={"limit": 1, "apply": False})
    assert res.status_code == 401


def test_api_review_list_unauthorized(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    assert client.get("/api/review/summary").status_code == 401


def test_health_still_public(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    assert client.get("/health").status_code == 200


def test_unsigned_tenant_cookie_rejected(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    res = client.get("/api/status", headers={"Cookie": "tagsmith_tenant=1"})
    assert res.status_code == 401


def test_signed_session_cookie_authenticates(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _client(settings, monkeypatch)
    res = client.get("/api/status")
    assert res.status_code == 200


def test_docs_disabled_by_default(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    assert client.get("/docs").status_code == 404


def test_auth_debug_disabled_by_default(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    assert client.get("/auth/debug").status_code == 404


def test_cors_localhost_random_port_not_allowed(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    client = _unauth_client(settings, monkeypatch)
    res = client.options(
        "/api/status",
        headers={
            "Origin": "http://127.0.0.1:9999",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert res.headers.get("access-control-allow-origin") != "http://127.0.0.1:9999"


def test_run_sync_returns_409_when_lock_held(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    from tagsmith.api.deps import gmail_dep
    from tagsmith.services.sync_lock import sync_flight

    client = _client(settings, monkeypatch)
    app = client.app
    app.dependency_overrides[gmail_dep] = lambda: FakeGmail()  # type: ignore[index]
    with sync_flight(blocking=False):
        res = client.post(
            "/api/sync/run",
            json={"limit": 1, "apply": False, "incremental": False},
        )
    assert res.status_code == 409
    assert res.json()["detail"] == "already_running"
    app.dependency_overrides.clear()


def test_background_tick_skips_when_lock_held(
    settings: Settings, session, fake_gmail: FakeGmail
) -> None:
    import asyncio

    from tagsmith.scheduler import run_schedule_tick
    from tagsmith.services.sync_lock import sync_flight

    async def _run() -> None:
        with sync_flight(blocking=False):
            tick = await run_schedule_tick(
                session, fake_gmail, settings, apply=False, renew_watch=False
            )
        assert "already_running" in tick.errors

    asyncio.run(_run())


def test_oauth_callback_rejects_mismatched_state(settings: Settings, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    settings = settings.model_copy(update={"token_encryption_key": "test-token-secret"})
    client = _unauth_client(settings, monkeypatch)
    res = client.get(
        "/auth/callback",
        params={"code": "abc", "state": "attacker"},
        headers={"Cookie": "oauth_state=legit"},
    )
    assert res.status_code == 400


def test_tenant_a_cannot_read_tenant_b_messages(settings: Settings, session) -> None:
    from tagsmith.db.models import Message, MessageState
    from tagsmith.review.queue import ReviewService

    session.add(Tenant(id=2, email="b@example.com"))
    session.add(
        Message(
            gmail_id="b-only",
            thread_id="tb",
            sender="b@b.com",
            subject="secret",
            state=MessageState.HELD,
            tenant_id=2,
        )
    )
    session.commit()
    held = ReviewService(session, tenant_id=1).list_held()
    assert all(m.gmail_id != "b-only" for m, _ in held)
    held_b = ReviewService(session, tenant_id=2).list_held()
    assert any(m.gmail_id == "b-only" for m, _ in held_b)


def test_sync_state_is_per_tenant(session, settings: Settings, fake_gmail: FakeGmail) -> None:
    from tagsmith.db.models import SyncState
    from tagsmith.services.sync import SyncService

    a = SyncService(session, fake_gmail, settings, tenant_id=1)
    b = SyncService(session, fake_gmail, settings, tenant_id=2)
    sa = a.get_sync_state()
    sb = b.get_sync_state()
    sa.history_id = "aaa"
    sb.history_id = "bbb"
    session.commit()
    assert session.get(SyncState, 1).history_id == "aaa"  # type: ignore[union-attr]
    assert session.get(SyncState, 2).history_id == "bbb"  # type: ignore[union-attr]


def test_web_package_json_present() -> None:
    from pathlib import Path

    assert Path("web/package.json").is_file()
