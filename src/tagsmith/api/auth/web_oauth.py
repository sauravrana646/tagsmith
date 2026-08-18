"""Web OAuth authorization-code flow for Phase 5."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlencode

import httpx
from google.oauth2.credentials import Credentials

from tagsmith.config import Settings
from tagsmith.gmail.auth import SCOPES
from tagsmith.security.crypto import decrypt_secret, encrypt_secret

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://www.googleapis.com/oauth2/v3/userinfo"


@dataclass
class OAuthClientConfig:
    client_id: str
    client_secret: str
    redirect_uri: str
    client_type: Literal["web", "installed", "unknown"] = "unknown"


def load_web_oauth_client(settings: Settings) -> OAuthClientConfig:
    """Resolve web client id/secret from settings or credentials JSON.

    Prefer a GCP **Web application** client. Desktop ``installed`` clients often
    hang or reject custom redirect URIs in the browser flow.
    """
    client_id = settings.google_web_client_id
    client_secret = settings.google_web_client_secret
    client_type: Literal["web", "installed", "unknown"] = "unknown"
    if not client_id or not client_secret:
        path = Path(settings.google_client_secret_path).expanduser()
        if path.exists():
            data = json.loads(path.read_text(encoding="utf-8"))
            if "web" in data and isinstance(data["web"], dict):
                block = data["web"]
                client_type = "web"
            elif "installed" in data and isinstance(data["installed"], dict):
                block = data["installed"]
                client_type = "installed"
            else:
                block = {}
            client_id = client_id or str(block.get("client_id") or "")
            client_secret = client_secret or str(block.get("client_secret") or "")
    elif settings.google_web_client_id:
        client_type = "web"
    if not client_id or not client_secret:
        raise RuntimeError(
            "Web OAuth client not configured. Create a GCP OAuth client of type "
            "**Web application**, add redirect URI "
            f"{settings.api_public_base_url.rstrip('/')}/auth/callback, "
            "then set TAGSMITH_GOOGLE_WEB_CLIENT_ID/SECRET (or put a `web` block "
            "in credentials.json)."
        )
    redirect = settings.api_public_base_url.rstrip("/") + settings.google_oauth_redirect_path
    return OAuthClientConfig(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect,
        client_type=client_type,
    )


def make_authorize_url(
    settings: Settings,
    *,
    state: str | None = None,
    prompt: str = "select_account",
) -> tuple[str, str]:
    """Build Google authorize URL.

    Default ``prompt=select_account`` avoids re-consent loops that can look like
    accounts.google.com is stuck loading. Pass ``prompt=consent`` when you need
    a fresh refresh token.
    """
    cfg = load_web_oauth_client(settings)
    state = state or secrets.token_urlsafe(24)
    params = {
        "client_id": cfg.client_id,
        "redirect_uri": cfg.redirect_uri,
        "response_type": "code",
        "scope": " ".join([*SCOPES, "openid", "email", "profile"]),
        "access_type": "offline",
        "include_granted_scopes": "true",
        "prompt": prompt,
        "state": state,
    }
    return f"{GOOGLE_AUTH_URL}?{urlencode(params)}", state


def oauth_debug_info(settings: Settings) -> dict[str, Any]:
    """Safe diagnostics for /auth/debug (no secrets)."""
    try:
        cfg = load_web_oauth_client(settings)
        return {
            "ok": True,
            "client_type": cfg.client_type,
            "client_id_suffix": cfg.client_id[-12:] if cfg.client_id else None,
            "redirect_uri": cfg.redirect_uri,
            "web_app_url": settings.web_app_url,
            "api_public_base_url": settings.api_public_base_url,
            "token_encryption_key_set": bool(settings.token_encryption_key),
            "warning": (
                None
                if cfg.client_type == "web"
                else (
                    "Using a Desktop (installed) OAuth client for the browser flow. "
                    "Create a Web application client in Google Cloud Console and add "
                    f"Authorized redirect URI: {cfg.redirect_uri}"
                )
            ),
            "checklist": [
                "GCP → APIs & Services → Credentials → OAuth 2.0 Client IDs",
                "Client type must be: Web application (not Desktop)",
                f"Authorized redirect URIs must include exactly: {cfg.redirect_uri}",
                "Use 127.0.0.1 consistently (not localhost) unless both are listed",
                f"After login you should land on: {settings.web_app_url}",
                "Review dashboard works without Sign in (lists SQLite queues)",
            ],
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def exchange_code(settings: Settings, code: str) -> dict[str, Any]:
    cfg = load_web_oauth_client(settings)
    with httpx.Client(timeout=30.0) as client:
        resp = client.post(
            GOOGLE_TOKEN_URL,
            data={
                "code": code,
                "client_id": cfg.client_id,
                "client_secret": cfg.client_secret,
                "redirect_uri": cfg.redirect_uri,
                "grant_type": "authorization_code",
            },
        )
        resp.raise_for_status()
        return dict(resp.json())


def fetch_userinfo(access_token: str) -> dict[str, Any]:
    with httpx.Client(timeout=30.0) as client:
        resp = client.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return dict(resp.json())


def credentials_from_token_response(
    settings: Settings,
    token_response: dict[str, Any],
) -> Credentials:
    cfg = load_web_oauth_client(settings)
    return Credentials(  # type: ignore[no-untyped-call]
        token=token_response.get("access_token"),
        refresh_token=token_response.get("refresh_token"),
        token_uri=GOOGLE_TOKEN_URL,
        client_id=cfg.client_id,
        client_secret=cfg.client_secret,
        scopes=SCOPES,
    )


def encrypt_refresh_token(settings: Settings, refresh_token: str) -> str:
    return encrypt_secret(refresh_token, secret_key=settings.token_encryption_key)


def decrypt_refresh_token(settings: Settings, ciphertext: str) -> str:
    return decrypt_secret(ciphertext, secret_key=settings.token_encryption_key)
