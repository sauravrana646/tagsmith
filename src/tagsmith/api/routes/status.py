"""Local operator / Gmail auth status for the dashboard."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlmodel import Session

from tagsmith.api.deps import require_session, session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.gmail.auth import AuthError, get_credentials
from tagsmith.rag.index import rag_status_payload

router = APIRouter(
    prefix="/api/status",
    tags=["status"],
    dependencies=[Depends(require_session)],
)


@router.get("")
def status(
    settings: Settings = Depends(settings_dep),
    session: Session = Depends(session_dep),
) -> dict[str, Any]:
    gmail_ok = False
    gmail_detail = "Not authenticated"
    try:
        creds = get_credentials(settings, interactive=False)
        gmail_ok = bool(creds and creds.valid)
        gmail_detail = "Desktop token ready (CLI `tagsmith auth`)" if gmail_ok else "Token invalid"
    except AuthError as exc:
        gmail_detail = str(exc)
    payload: dict[str, Any] = {
        "gmail_authenticated": gmail_ok,
        "gmail_detail": gmail_detail,
        "web_app_url": settings.web_app_url,
        "api_public_base_url": settings.api_public_base_url,
        "enable_rag": settings.enable_rag,
        "label_parent": settings.label_parent,
        "hint": (
            "UI mutations with Apply write to Gmail using your desktop token. "
            "Run `uv run tagsmith auth` once if gmail_authenticated is false."
        ),
    }
    payload.update(rag_status_payload(session, settings))
    return payload
