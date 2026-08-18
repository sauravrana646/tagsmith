"""Signed session cookies for the API (HMAC-SHA256)."""

from __future__ import annotations

import hashlib
import hmac
import time

from tagsmith.config import Settings

SESSION_COOKIE = "tagsmith_tenant"
SESSION_MAX_AGE = 60 * 60 * 24 * 30
CSRF_HEADER = "x-tagsmith-requested-with"
CSRF_HEADER_VALUE = "dashboard"


class SessionError(ValueError):
    pass


def signing_key(settings: Settings) -> str:
    key = settings.session_signing_key or settings.token_encryption_key
    if not key:
        raise SessionError("TAGSMITH_SESSION_SIGNING_KEY is required")
    return key


def sign_session_value(tenant_id: int, secret: str, *, issued_at: int | None = None) -> str:
    issued = issued_at if issued_at is not None else int(time.time())
    payload = f"{tenant_id}.{issued}"
    digest = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{digest}"


def verify_session_value(token: str, secret: str, *, max_age: int = SESSION_MAX_AGE) -> int:
    parts = token.split(".")
    if len(parts) != 3:
        raise SessionError("invalid session cookie")
    tenant_raw, issued_raw, digest = parts
    payload = f"{tenant_raw}.{issued_raw}"
    expected = hmac.new(secret.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(digest, expected):
        raise SessionError("invalid session signature")
    try:
        tenant_id = int(tenant_raw)
        issued = int(issued_raw)
    except ValueError as exc:
        raise SessionError("invalid session payload") from exc
    if issued < 0 or tenant_id < 1:
        raise SessionError("invalid session payload")
    if int(time.time()) - issued > max_age:
        raise SessionError("session expired")
    return tenant_id
