"""Register production API routers on the FastAPI app."""
from __future__ import annotations

from fastapi import FastAPI

from app.routes import ai_reasoning, fairness, gameplay, governance, grading, health, institutional, moderation, replay, runtime


def register_production_routers(app: FastAPI) -> None:
    from app.ops.middleware import CorrelationMiddleware
    from app.security.middleware import SecurityAbuseMiddleware
    from app.security.secret_loader import hydrate_env_from_vault

    hydrate_env_from_vault()
    app.add_middleware(SecurityAbuseMiddleware)
    app.add_middleware(CorrelationMiddleware)
    app.include_router(health.router)
    app.include_router(institutional.router)
    app.include_router(moderation.router)
    from app.routes import auth_sso, operations, security

    app.include_router(auth_sso.router)
    app.include_router(operations.router)
    app.include_router(security.router)
    from app.routes import contracts

    app.include_router(contracts.router)
    app.include_router(governance.router)
    app.include_router(governance.appeals_router)
    app.include_router(grading.router)
    app.include_router(fairness.router)
    app.include_router(gameplay.router)
    app.include_router(ai_reasoning.router)
    app.include_router(runtime.router)
    app.include_router(replay.router)
    from app.governance_ui.routes import register_governance_ui

    register_governance_ui(app)
