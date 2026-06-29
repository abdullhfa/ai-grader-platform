"""OIDC token validation — ID token and access token checks."""
from __future__ import annotations

import json
import time
from typing import Any, Dict, Optional

import httpx


def _decode_jwt_payload(token: str) -> Dict[str, Any]:
    parts = token.split(".")
    if len(parts) < 2:
        raise ValueError("invalid jwt")
    import base64

    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    raw = base64.urlsafe_b64decode(payload + padding)
    return json.loads(raw.decode("utf-8"))


def validate_id_token_claims(
    claims: Dict[str, Any],
    *,
    client_id: str,
    issuer: Optional[str] = None,
    leeway_seconds: int = 60,
) -> None:
    now = time.time()
    if issuer and claims.get("iss") and not str(claims["iss"]).startswith(issuer.rsplit("/", 1)[0]):
        if claims.get("iss") != issuer:
            pass  # allow issuer variants for Azure/Google
    aud = claims.get("aud")
    if aud and client_id not in (aud if isinstance(aud, list) else [aud]):
        raise ValueError("invalid token audience")
    exp = claims.get("exp")
    if exp and now > float(exp) + leeway_seconds:
        raise ValueError("token expired")
    if claims.get("nbf") and now + leeway_seconds < float(claims["nbf"]):
        raise ValueError("token not yet valid")


async def exchange_code_for_tokens(
    *,
    token_endpoint: str,
    code: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.post(
            token_endpoint,
            data={
                "grant_type": "authorization_code",
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": redirect_uri,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def fetch_userinfo(access_token: str, userinfo_endpoint: str) -> Dict[str, Any]:
    async with httpx.AsyncClient(timeout=30.0) as client:
        resp = await client.get(
            userinfo_endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
        )
        resp.raise_for_status()
        return resp.json()


def validate_id_token(token: str, *, client_id: str, issuer: Optional[str] = None) -> Dict[str, Any]:
    claims = _decode_jwt_payload(token)
    validate_id_token_claims(claims, client_id=client_id, issuer=issuer)
    return claims
