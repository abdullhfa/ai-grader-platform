"""OIDC/OAuth2 provider configuration — Azure AD, Google, generic."""
from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Dict, Optional
from urllib.parse import urlencode


@dataclass(frozen=True)
class OidcProviderConfig:
    name: str
    issuer: str
    client_id: str
    client_secret: str
    redirect_uri: str
    scopes: str = "openid email profile"
    authorization_endpoint: Optional[str] = None
    token_endpoint: Optional[str] = None
    userinfo_endpoint: Optional[str] = None
    jwks_uri: Optional[str] = None

    @property
    def auth_url(self) -> str:
        base = self.authorization_endpoint or f"{self.issuer.rstrip('/')}/oauth2/v2.0/authorize"
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": self.scopes,
            "response_mode": "query",
        }
        return f"{base}?{urlencode(params)}"


def _env(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def get_active_oidc_provider() -> Optional[OidcProviderConfig]:
    provider = _env("AI_GRADER_SSO_PROVIDER").lower()
    if not provider:
        return None

    if provider == "azure":
        tenant = _env("AI_GRADER_AZURE_TENANT_ID", "common")
        issuer = f"https://login.microsoftonline.com/{tenant}/v2.0"
        return OidcProviderConfig(
            name="azure",
            issuer=issuer,
            client_id=_env("AI_GRADER_AZURE_CLIENT_ID"),
            client_secret=_env("AI_GRADER_AZURE_CLIENT_SECRET"),
            redirect_uri=_env("AI_GRADER_SSO_REDIRECT_URI", "http://localhost:8000/auth/oidc/callback"),
            authorization_endpoint=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/authorize",
            token_endpoint=f"https://login.microsoftonline.com/{tenant}/oauth2/v2.0/token",
            userinfo_endpoint="https://graph.microsoft.com/oidc/userinfo",
            jwks_uri=f"https://login.microsoftonline.com/{tenant}/discovery/v2.0/keys",
        )

    if provider in ("google", "google_workspace"):
        return OidcProviderConfig(
            name="google",
            issuer="https://accounts.google.com",
            client_id=_env("GOOGLE_CLIENT_ID") or _env("AI_GRADER_GOOGLE_CLIENT_ID"),
            client_secret=_env("GOOGLE_CLIENT_SECRET") or _env("AI_GRADER_GOOGLE_CLIENT_SECRET"),
            redirect_uri=_env("GOOGLE_REDIRECT_URI") or _env("AI_GRADER_SSO_REDIRECT_URI"),
            authorization_endpoint="https://accounts.google.com/o/oauth2/v2/auth",
            token_endpoint="https://oauth2.googleapis.com/token",
            userinfo_endpoint="https://openidconnect.googleapis.com/v1/userinfo",
        )

    issuer = _env("AI_GRADER_OIDC_ISSUER")
    if provider == "oidc" and issuer:
        return OidcProviderConfig(
            name="oidc",
            issuer=issuer,
            client_id=_env("AI_GRADER_OIDC_CLIENT_ID"),
            client_secret=_env("AI_GRADER_OIDC_CLIENT_SECRET"),
            redirect_uri=_env("AI_GRADER_SSO_REDIRECT_URI"),
            authorization_endpoint=_env("AI_GRADER_OIDC_AUTH_URL") or None,
            token_endpoint=_env("AI_GRADER_OIDC_TOKEN_URL") or None,
            userinfo_endpoint=_env("AI_GRADER_OIDC_USERINFO_URL") or None,
            jwks_uri=_env("AI_GRADER_OIDC_JWKS_URL") or None,
        )
    return None


def sso_enabled() -> bool:
    cfg = get_active_oidc_provider()
    return bool(cfg and cfg.client_id and cfg.client_secret)
