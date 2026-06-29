"""Health and readiness routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.database import SessionLocal, get_db
from app.institutional.readiness_report import build_institutional_readiness_report
from app.production.hardening import build_health_status

router = APIRouter(tags=["health"])


@router.get("/health")
@router.get("/api/health")
async def health_check():
    """Quick liveness + production feature flags."""
    from app.production.hardening import build_health_status as _quick

    quick = _quick(db_ok=True)
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        quick["checks"] = {"database": {"ok": True}}
    except Exception as exc:
        quick["status"] = "degraded"
        quick["checks"] = {"database": {"ok": False, "error": str(exc)}}
    code = 200 if quick.get("status") == "ok" else 503
    return JSONResponse(quick, status_code=code)


@router.get("/health/deep")
async def health_check_deep():
    """Deep health — AI provider, templates, database."""
    from app.ai_provider import check_provider_health
    from app.pearson_templates import pearson_templates_status

    health = {"status": "ok", "checks": {}}
    try:
        ai_info = check_provider_health()
        health["checks"]["ai_provider"] = ai_info
        if not ai_info.get("ok"):
            health["status"] = "degraded"
    except Exception as exc:
        health["checks"]["ai_provider"] = {"ok": False, "error": str(exc)}
        health["status"] = "degraded"

    _pt = pearson_templates_status("DEFAULT")
    health["checks"]["pearson_templates"] = {
        "ready_count": _pt["ready_count"],
        "total_count": _pt["total_count"],
        "ok": _pt["ready_count"] >= 4,
    }
    if _pt["ready_count"] < 4:
        health["status"] = "degraded"

    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        health["checks"]["database"] = {"ok": True}
    except Exception as exc:
        health["checks"]["database"] = {"ok": False, "error": str(exc)}
        health["status"] = "degraded"

    code = 200 if health["status"] == "ok" else 503
    return JSONResponse(health, status_code=code)


@router.get("/metrics")
@router.get("/api/metrics")
async def prometheus_metrics():
    """Prometheus text metrics — PHASE E."""
    from fastapi.responses import PlainTextResponse

    from app.observability.metrics import metrics

    return PlainTextResponse(metrics.prometheus_text(), media_type="text/plain; version=0.0.4")


@router.get("/ready")
@router.get("/api/ready")
async def readiness_check(db: Session = Depends(get_db)):
    report = build_institutional_readiness_report(db)
    status_code = 200 if report.get("readiness_score", 0) >= 50 else 503
    return JSONResponse(content=report, status_code=status_code)
