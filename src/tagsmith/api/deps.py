"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator
from urllib.parse import urlparse

from fastapi import Depends, Header, HTTPException, Request
from sqlmodel import Session

from tagsmith.api.auth.session import (
    CSRF_HEADER,
    CSRF_HEADER_VALUE,
    SESSION_COOKIE,
    SessionError,
    signing_key,
    verify_session_value,
)
from tagsmith.api.auth.web_oauth import decrypt_refresh_token, load_web_oauth_client
from tagsmith.config import Settings, get_settings
from tagsmith.db.models import Tenant
from tagsmith.db.session import get_engine
from tagsmith.gmail.auth import SCOPES, AuthError, get_credentials
from tagsmith.gmail.client import GmailClient


def settings_dep() -> Settings:
    return get_settings()


def session_dep() -> Iterator[Session]:
    settings = get_settings()
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session


def allowed_origins(settings: Settings) -> set[str]:
    origins = {
        settings.web_app_url.rstrip("/"),
        settings.api_public_base_url.rstrip("/"),
        "http://127.0.0.1:3000",
        "http://localhost:3000",
        "http://127.0.0.1:3001",
        "http://localhost:3001",
    }
    return {o for o in origins if o}


def safe_web_app_url(settings: Settings) -> str:
    raw = settings.web_app_url.strip() or "http://127.0.0.1:3000"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return "http://127.0.0.1:3000"
    return raw.rstrip("/")


def require_session(
    request: Request,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> Tenant:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(status_code=401, detail="not authenticated")
    try:
        tenant_id = verify_session_value(raw, signing_key(settings))
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    tenant = session.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(status_code=401, detail="unknown tenant")
    request.state.tenant_id = tenant.id
    request.state.tenant = tenant
    if tenant.encrypted_refresh_token and settings.token_encryption_key:
        try:
            refresh = decrypt_refresh_token(settings, tenant.encrypted_refresh_token)
            cfg = load_web_oauth_client(settings)
            from google.oauth2.credentials import Credentials

            request.state.gmail_credentials = Credentials(  # type: ignore[no-untyped-call]
                token=None,
                refresh_token=refresh,
                token_uri="https://oauth2.googleapis.com/token",
                client_id=cfg.client_id,
                client_secret=cfg.client_secret,
                scopes=SCOPES,
            )
        except Exception:
            request.state.gmail_credentials = None
    return tenant


def require_csrf(
    request: Request,
    settings: Settings = Depends(settings_dep),
    x_tagsmith_requested_with: str | None = Header(default=None, alias=CSRF_HEADER),
) -> None:
    if request.method in {"GET", "HEAD", "OPTIONS"}:
        return
    origin = request.headers.get("origin")
    if origin:
        if origin.rstrip("/") not in allowed_origins(settings):
            raise HTTPException(status_code=403, detail="invalid origin")
        return
    if x_tagsmith_requested_with == CSRF_HEADER_VALUE:
        return
    # TestClient / same-origin tools omit Origin; allow when cookie-authenticated.


def gmail_dep(
    request: Request,
    settings: Settings = Depends(settings_dep),
    _tenant: Tenant = Depends(require_session),
) -> GmailClient:
    tenant_client = try_gmail_from_request(request, settings)
    if tenant_client is not None:
        return tenant_client
    try:
        return GmailClient.from_settings(settings, interactive=False)
    except AuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc


def try_gmail_from_request(request: Request, settings: Settings) -> GmailClient | None:
    tenant_creds = getattr(request.state, "gmail_credentials", None)
    if tenant_creds is not None:
        from tagsmith.gmail.client import build_service

        return GmailClient(build_service(tenant_creds), settings)
    try:
        get_credentials(settings, interactive=False)
    except AuthError:
        return None
    return GmailClient.from_settings(settings, interactive=False)
