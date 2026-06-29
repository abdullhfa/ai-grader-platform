"""Application secrets and cookie hardening."""
from __future__ import annotations

import logging
import os
import secrets

logger = logging.getLogger("ai_grader.security")

_DEV_FALLBACK = "dev-lock-secret"


def get_app_secret() -> str:
    """HMAC / signing secret — never use dev fallback in production."""
    secret = (
        os.getenv("SECRET_KEY")
        or os.getenv("SUBSCRIPTION_LOCK_SECRET")
        or ""
    ).strip()
    if secret and secret != _DEV_FALLBACK:
        return secret
    if os.getenv("PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
        raise RuntimeError(
            "SECRET_KEY must be set to a strong random value when PRODUCTION=true"
        )
    logger.warning(
        "SECRET_KEY not configured — using insecure dev fallback. "
        "Set SECRET_KEY before deploying."
    )
    return _DEV_FALLBACK


def cookie_secure_flag() -> bool:
    """True when cookies should be HTTPS-only."""
    if os.getenv("COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes"):
        return True
    if os.getenv("PRODUCTION", "").strip().lower() in ("1", "true", "yes"):
        return True
    return False


def session_cookie_kwargs(*, max_age: int = 86400) -> dict:
    return {
        "httponly": True,
        "max_age": max_age,
        "samesite": "lax",
        "secure": cookie_secure_flag(),
    }


def generate_secret_key_hint() -> str:
    return secrets.token_urlsafe(48)
