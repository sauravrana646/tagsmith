"""Web OAuth routes (Phase 5)."""

from __future__ import annotations

import hmac
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlmodel import Session, select

from tagsmith.api.auth.session import (
    SESSION_COOKIE,
    SESSION_MAX_AGE,
    SessionError,
    sign_session_value,
    signing_key,
    verify_session_value,
)
from tagsmith.api.auth.web_oauth import (
    encrypt_refresh_token,
    exchange_code,
    fetch_userinfo,
    make_authorize_url,
    oauth_debug_info,
)
from tagsmith.api.deps import safe_web_app_url, session_dep, settings_dep
from tagsmith.config import Settings
from tagsmith.db.models import Tenant, utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_session_cookie(
    response: Response, tenant_id: int, settings: Settings, *, request: Request | None = None
) -> None:
    secret = signing_key(settings)
    value = sign_session_value(tenant_id, secret)
    secure = settings.cookie_secure
    if request is not None and request.url.scheme == "https":
        secure = True
    response.set_cookie(
        key=SESSION_COOKIE,
        value=value,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=SESSION_MAX_AGE,
        path="/",
    )


def _clear_session_cookie(response: Response) -> None:
    response.delete_cookie(SESSION_COOKIE, path="/")


def _tenant_from_request(request: Request, session: Session, settings: Settings) -> Tenant | None:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        return None
    try:
        tenant_id = verify_session_value(raw, signing_key(settings))
    except SessionError:
        return None
    return session.get(Tenant, tenant_id)


def _me_payload(tenant: Tenant | None) -> dict[str, Any]:
    if tenant is None:
        return {"authenticated": False}
    return {
        "authenticated": True,
        "tenant_id": tenant.id,
        "email": tenant.email,
        "name": tenant.display_name or tenant.email.split("@")[0],
        "picture_url": tenant.picture_url,
        "plan": tenant.plan,
        "has_refresh_token": bool(tenant.encrypted_refresh_token),
    }


@router.get("/debug")
def auth_debug(settings: Settings = Depends(settings_dep)) -> dict[str, Any]:
    """Print OAuth config checklist (no secrets). Disabled unless explicitly enabled."""
    if not settings.enable_auth_debug:
        raise HTTPException(404, "Not Found")
    return oauth_debug_info(settings)


@router.get("/login", response_model=None)
def login(
    request: Request,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
    prompt: str = Query("select_account", description="select_account | consent | none"),
    force: bool = Query(False, description="Force Google account picker even if signed in"),
) -> RedirectResponse | HTMLResponse:
    """Start Google OAuth, or bounce home if a valid session cookie already exists."""
    dest_base = safe_web_app_url(settings)
    existing = _tenant_from_request(request, session, settings)
    if existing is not None and not force:
        return RedirectResponse(dest_base + "/?auth=already")

    try:
        url, state = make_authorize_url(settings, prompt=prompt)
    except RuntimeError as exc:
        import html as html_lib

        dash = html_lib.escape(dest_base)
        safe = html_lib.escape(str(exc))
        debug_link = "/auth/debug" if settings.enable_auth_debug else "/health"
        return HTMLResponse(
            status_code=500,
            content=f"""<!doctype html>
<html><head><meta charset="utf-8"><title>Tagsmith sign-in</title>
<style>
  body{{font-family:system-ui,sans-serif;max-width:40rem;margin:3rem auto;
    padding:0 1rem;color:#171717;line-height:1.5}}
  code{{background:#f5f5f5;padding:.1rem .35rem;border-radius:4px}}
  a.btn{{display:inline-block;margin-top:1rem;padding:.55rem .9rem;
    background:#171717;color:#fff;border-radius:6px;text-decoration:none;font-weight:600}}
  .box{{border:1px solid #e5e5e5;border-radius:8px;padding:1rem;background:#fafafa}}
</style></head><body>
  <h1>Sign-in not configured</h1>
  <div class="box"><p>{safe}</p></div>
  <p>For local review you can keep using the dashboard with a desktop token
  (<code>uv run tagsmith auth</code>) — web Google sign-in is optional.</p>
  <a class="btn" href="{dash}">Back to dashboard</a>
  <p><a href="{html_lib.escape(debug_link)}">Diagnostics</a></p>
</body></html>""",
        )
    response = RedirectResponse(url)
    secure = settings.cookie_secure or request.url.scheme == "https"
    response.set_cookie(
        "oauth_state",
        state,
        httponly=True,
        samesite="lax",
        secure=secure,
        max_age=600,
        path="/",
    )
    return response


@router.get("/callback")
def callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> RedirectResponse:
    cookie_state = request.cookies.get("oauth_state")
    if not cookie_state or not hmac.compare_digest(cookie_state, state):
        raise HTTPException(400, "OAuth state mismatch")
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
    name = str(info.get("name") or info.get("given_name") or "") or None
    picture = str(info.get("picture") or "") or None
    if not email:
        raise HTTPException(400, "Google userinfo missing email")

    tenant = session.exec(select(Tenant).where(Tenant.email == email)).first()
    if tenant is None:
        tenant = Tenant(email=email, google_sub=sub, display_name=name, picture_url=picture)
        session.add(tenant)
    else:
        tenant.google_sub = sub or tenant.google_sub
        tenant.display_name = name or tenant.display_name
        tenant.picture_url = picture or tenant.picture_url
        tenant.updated_at = utcnow()

    if refresh:
        tenant.encrypted_refresh_token = encrypt_refresh_token(settings, str(refresh))
    session.commit()
    session.refresh(tenant)

    dest = safe_web_app_url(settings) + "/?auth=ok"
    redirect = RedirectResponse(dest)
    assert tenant.id is not None
    _set_session_cookie(redirect, tenant.id, settings, request=request)
    redirect.delete_cookie("oauth_state", path="/")
    return redirect


@router.get("/me")
def me(
    request: Request,
    session: Session = Depends(session_dep),
    settings: Settings = Depends(settings_dep),
) -> dict[str, Any]:
    return _me_payload(_tenant_from_request(request, session, settings))


@router.post("/logout")
def logout() -> Response:
    response = Response(content='{"ok":true}', media_type="application/json")
    _clear_session_cookie(response)
    return response
