"""Web OAuth routes (Phase 5)."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse
from sqlmodel import Session, select

from tagsmith.api.auth.web_oauth import (
    encrypt_refresh_token,
    exchange_code,
    fetch_userinfo,
    make_authorize_url,
)
from tagsmith.api.deps import session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.db.models import Tenant, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


@router.get("/login")
def login(settings: Settings = Depends(settings_dep)) -> RedirectResponse:
    try:
        url, state = make_authorize_url(settings)
    except RuntimeError as exc:
        raise HTTPException(500, str(exc)) from exc
    response = RedirectResponse(url)
    response.set_cookie("oauth_state", state, httponly=True, samesite="lax", max_age=600)
    return response


@router.get("/callback")
def callback(
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> RedirectResponse:
    if not settings.token_encryption_key:
        raise HTTPException(
            500,
            "TAGSMITH_TOKEN_ENCRYPTION_KEY is required before accepting web OAuth callbacks",
        )
    try:
        token_response = exchange_code(settings, code)
        access = str(token_response.get("access_token") or "")
        refresh = token_response.get("refresh_token")
        info = fetch_userinfo(access) if access else {}
    except Exception as exc:
        raise HTTPException(400, f"OAuth exchange failed: {exc}") from exc

    email = str(info.get("email") or "")
    sub = str(info.get("sub") or "") or None
    if not email:
        raise HTTPException(400, "Google userinfo missing email")

    tenant = session.exec(select(Tenant).where(Tenant.email == email)).first()
    if tenant is None:
        tenant = Tenant(email=email, google_sub=sub)
        session.add(tenant)
    else:
        tenant.google_sub = sub or tenant.google_sub
        tenant.updated_at = utcnow()

    if refresh:
        tenant.encrypted_refresh_token = encrypt_refresh_token(settings, str(refresh))
    session.commit()
    session.refresh(tenant)

    redirect = RedirectResponse("/?auth=ok")
    redirect.set_cookie(
        "tagsmith_tenant",
        str(tenant.id),
        httponly=True,
        samesite="lax",
        max_age=60 * 60 * 24 * 30,
    )
    return redirect


@router.get("/me")
def me(
    request: Request,
    session: Session = Depends(session_dep),
) -> dict[str, Any]:
    tenant_id = request.cookies.get("tagsmith_tenant") or getattr(request.state, "tenant_id", None)
    if not tenant_id:
        return {"authenticated": False}
    tenant = session.get(Tenant, int(tenant_id))
    if tenant is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "tenant_id": tenant.id,
        "email": tenant.email,
        "plan": tenant.plan,
        "has_refresh_token": bool(tenant.encrypted_refresh_token),
    }
