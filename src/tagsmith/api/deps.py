"""FastAPI dependencies."""

from __future__ import annotations

from collections.abc import Iterator

from fastapi import Request
from sqlmodel import Session

from tagsmith.config import Settings, get_settings
from tagsmith.db.session import get_engine
from tagsmith.gmail.auth import AuthError, get_credentials
from tagsmith.gmail.client import GmailClient


def settings_dep() -> Settings:
    return get_settings()


def session_dep() -> Iterator[Session]:
    settings = get_settings()
    engine = get_engine(settings)
    with Session(engine) as session:
        yield session


def gmail_dep(settings: Settings | None = None) -> GmailClient:
    from fastapi import HTTPException

    settings = settings or get_settings()
    try:
        # Prefer desktop token for local single-user; multi-tenant path uses request state.
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
