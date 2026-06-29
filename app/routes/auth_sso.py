"""Institutional SSO routes — OIDC gateway → RBAC → governance permissions."""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.auth import create_session, google_login_or_register
from app.auth.audit_identity import log_identity_event
from app.auth.oidc_provider import get_active_oidc_provider, sso_enabled
from app.auth.permissions_store import assign_user_role, get_primary_governance_role, seed_rbac_defaults
from app.auth.role_mapper import claims_to_user_profile, map_claims_to_roles
from app.auth.token_validation import exchange_code_for_tokens, fetch_userinfo, validate_id_token
from app.database import get_db
from app.models import User
from app.ops.correlation import get_correlation

router = APIRouter(prefix="/auth", tags=["sso"])


@router.get("/oidc/login")
async def oidc_login():
    cfg = get_active_oidc_provider()
    if not cfg or not cfg.client_id:
        raise HTTPException(status_code=503, detail="SSO not configured")
    return RedirectResponse(url=cfg.auth_url, status_code=302)


@router.get("/oidc/callback")
async def oidc_callback(request: Request, db: Session = Depends(get_db)):
    cfg = get_active_oidc_provider()
    if not cfg:
        raise HTTPException(status_code=503, detail="SSO not configured")

    code = request.query_params.get("code")
    if not code:
        return RedirectResponse(url="/login?error=sso_failed", status_code=302)

    seed_rbac_defaults(db)
    trace = get_correlation().trace_id if get_correlation() else None

    try:
        tokens = await exchange_code_for_tokens(
            token_endpoint=cfg.token_endpoint or f"{cfg.issuer}/token",
            code=code,
            client_id=cfg.client_id,
            client_secret=cfg.client_secret,
            redirect_uri=cfg.redirect_uri,
        )
    except Exception:
        return RedirectResponse(url="/login?error=sso_token_failed", status_code=302)

    claims = {}
    if tokens.get("id_token"):
        try:
            from app.auth.token_validation import validate_id_token

            claims = validate_id_token(tokens["id_token"], client_id=cfg.client_id, issuer=cfg.issuer)
        except Exception:
            claims = {}

    if not claims and tokens.get("access_token") and cfg.userinfo_endpoint:
        try:
            claims = await fetch_userinfo(tokens["access_token"], cfg.userinfo_endpoint)
        except Exception:
            return RedirectResponse(url="/login?error=sso_userinfo_failed", status_code=302)

    profile = claims_to_user_profile(claims)
    if not profile.get("email"):
        return RedirectResponse(url="/login?error=sso_no_email", status_code=302)

    user = google_login_or_register(
        db,
        google_id=profile["sub"],
        email=profile["email"],
        first_name=profile.get("first_name") or "",
        last_name=profile.get("last_name") or "",
    )
    if not user:
        return RedirectResponse(url="/login?error=sso_user_failed", status_code=302)

    setattr(user, "login_method", cfg.name)
    db.commit()

    for role_name in map_claims_to_roles(claims):
        try:
            assign_user_role(db, user_id=int(user.id), role_name=role_name, source=cfg.name)
        except ValueError:
            pass

    log_identity_event(
        db,
        action="sso_login",
        user_id=int(user.id),
        email=user.email,
        provider=cfg.name,
        trace_id=trace,
        metadata={"roles": map_claims_to_roles(claims)},
    )
    try:
        from app.security.security_audit import log_security_action

        log_security_action(
            action="login",
            actor=user.email or str(user.id),
            resource=f"sso:{cfg.name}",
            trace_id=trace,
        )
    except Exception:
        pass

    session_id = create_session(int(user.id), trace_id=trace)
    response = RedirectResponse(url="/governance/examiner", status_code=302)
    response.set_cookie(key="session_id", value=session_id, httponly=True, max_age=86400, samesite="lax")
    return response


@router.get("/oidc/status")
async def oidc_status():
    cfg = get_active_oidc_provider()
    return {
        "enabled": sso_enabled(),
        "provider": cfg.name if cfg else None,
        "redirect_uri": cfg.redirect_uri if cfg else None,
    }


@router.get("/rbac/me")
async def rbac_me(request: Request, db: Session = Depends(get_db)):
    from app.auth import get_current_user

    user = get_current_user(request, db)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    seed_rbac_defaults(db)
    role = get_primary_governance_role(db, int(user.id))
    return {"user_id": user.id, "email": user.email, "governance_role": role}
