"""Signed CSRF tokens for HTML form POSTs."""
from __future__ import annotations

import hashlib
import hmac
import secrets
import time
from typing import Optional

from fastapi import HTTPException, Request  # type: ignore

from app.security.app_secrets import get_app_secret

_TOKEN_TTL = 86400
_COOKIE = "csrf_token"


def _sign(payload: str) -> str:
    sig = hmac.new(get_app_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def _verify(token: str) -> bool:
    if not token or "." not in token:
        return False
    payload, sig = token.rsplit(".", 1)
    expected = hmac.new(get_app_secret().encode(), payload.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(sig, expected):
        return False
    parts = payload.split("|")
    if len(parts) != 2:
        return False
    try:
        ts = int(parts[1])
    except ValueError:
        return False
    return (time.time() - ts) <= _TOKEN_TTL


def issue_csrf_token() -> str:
    return _sign(f"{secrets.token_urlsafe(16)}|{int(time.time())}")


def set_csrf_cookie(response, token: Optional[str] = None) -> str:
    """Attach CSRF cookie to response; return token value."""
    tok = token or issue_csrf_token()
    from app.security.app_secrets import cookie_secure_flag

    response.set_cookie(
        key=_COOKIE,
        value=tok,
        httponly=False,
        max_age=_TOKEN_TTL,
        samesite="lax",
        secure=cookie_secure_flag(),
    )
    return tok


def validate_csrf_request(request: Request, form_token: Optional[str] = None) -> None:
    """Double-submit: cookie must match form/header token."""
    cookie_tok = request.cookies.get(_COOKIE) or ""
    header_tok = request.headers.get("X-CSRF-Token") or ""
    body_tok = form_token or ""
    candidate = body_tok or header_tok
    if not candidate or not cookie_tok:
        raise HTTPException(status_code=403, detail="CSRF token missing")
    if not hmac.compare_digest(cookie_tok, candidate):
        raise HTTPException(status_code=403, detail="CSRF token invalid")
    if not _verify(cookie_tok):
        raise HTTPException(status_code=403, detail="CSRF token expired")
