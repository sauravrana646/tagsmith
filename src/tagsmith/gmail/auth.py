"""Desktop OAuth flow and credential persistence."""

from __future__ import annotations

from pathlib import Path
from typing import cast

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from tagsmith.config import Settings
from tagsmith.telemetry import get_logger

# Sensitive (not restricted) scopes — do not add mail.google.com.
SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.labels",
]

log = get_logger(__name__)


class AuthError(RuntimeError):
    pass


def load_credentials(settings: Settings) -> Credentials | None:
    token_path = settings.token_path
    if not token_path.exists():
        return None
    creds = cast(
        Credentials,
        Credentials.from_authorized_user_file(str(token_path), SCOPES),  # type: ignore[no-untyped-call]
    )
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())  # type: ignore[no-untyped-call]
        save_credentials(creds, token_path)
    return creds


def save_credentials(creds: Credentials, token_path: Path) -> None:
    token_path.parent.mkdir(parents=True, exist_ok=True)
    token_path.write_text(creds.to_json(), encoding="utf-8")  # type: ignore[no-untyped-call]


def run_auth_flow(settings: Settings) -> Credentials:
    secret = settings.google_client_secret_path.expanduser()
    if not secret.exists():
        raise AuthError(
            f"OAuth client secret not found at {secret}. "
            "Download a Desktop client JSON from Google Cloud Console and place it there "
            "(or set TAGSMITH_GOOGLE_CLIENT_SECRET_PATH)."
        )
    flow = InstalledAppFlow.from_client_secrets_file(str(secret), SCOPES)
    creds = cast(Credentials, flow.run_local_server(port=0, prompt="consent"))
    save_credentials(creds, settings.token_path)
    log.info("auth.success", token_path=str(settings.token_path))
    return creds


def get_credentials(settings: Settings, *, interactive: bool = False) -> Credentials:
    creds = load_credentials(settings)
    if creds and creds.valid:
        return creds
    if interactive:
        return run_auth_flow(settings)
    raise AuthError(
        "Not authenticated. Run `tagsmith auth` after placing your OAuth client JSON."
    )
