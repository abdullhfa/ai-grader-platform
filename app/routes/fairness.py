"""Fairness analytics routes."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, get_current_user_id
from app.database import get_db
from app.models import Submission
from app.routes.deps import app_title, get_templates, subscription_info_for_user
from app.services.subscription import get_subscription_info

router = APIRouter(tags=["fairness"])


def _batch_or_404(db: Session, batch_id: int):
    batch = db.query(models.BatchGrading).filter(models.BatchGrading.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return batch


@router.get("/api/fairness-analytics/evidence/batch/{batch_id}")
async def evidence_fairness_batch_api(
    batch_id: int,
    db: Session = Depends(get_db),
    fairness_epoch: str = "EVIDENCE_FAIRNESS_v1",
    metric_contract: str = "evidence_distribution_v1",
):
    from app.evidence_fairness_analytics import build_batch_evidence_fairness_report

    _batch_or_404(db, batch_id)
    return build_batch_evidence_fairness_report(
        db, batch_id, fairness_epoch=fairness_epoch, metric_contract=metric_contract
    )


@router.get("/api/fairness-analytics/procedural/batch/{batch_id}")
async def procedural_fairness_batch_api(
    batch_id: int,
    db: Session = Depends(get_db),
    procedural_epoch: str = "PROCEDURAL_ANALYTICS_v1",
    metric_contract: str = "procedural_flow_v1",
):
    from app.procedural_fairness_analytics import build_batch_procedural_fairness_report

    _batch_or_404(db, batch_id)
    return build_batch_procedural_fairness_report(
        db, batch_id, procedural_epoch=procedural_epoch, metric_contract=metric_contract
    )


@router.get("/api/fairness-analytics/disparity/batch/{batch_id}")
async def replay_disparity_batch_api(
    batch_id: int,
    db: Session = Depends(get_db),
    disparity_contract: str = "replay_disparity_v1",
    comparison_basis: str = "same_epoch_same_contract",
):
    from app.replay_disparity_analytics import build_batch_replay_disparity_report

    _batch_or_404(db, batch_id)
    return build_batch_replay_disparity_report(
        db, batch_id, disparity_contract=disparity_contract, comparison_basis=comparison_basis
    )


@router.get("/api/fairness-analytics/distribution/batch/{batch_id}")
async def statistical_distribution_batch_api(batch_id: int, db: Session = Depends(get_db)):
    from app.statistical_distribution_analytics import build_batch_statistical_distribution_report

    _batch_or_404(db, batch_id)
    return build_batch_statistical_distribution_report(db, batch_id)


@router.get("/api/fairness-analytics/governance-weighting/batch/{batch_id}")
async def governance_weighting_batch_api(batch_id: int, db: Session = Depends(get_db)):
    from app.governance_weighting import build_batch_governance_weighting_report

    _batch_or_404(db, batch_id)
    return build_batch_governance_weighting_report(db, batch_id)


@router.get("/api/replay-cohort-registry")
async def replay_cohort_registry_api():
    from app.replay_cohort_registry import list_cohort_registry

    return list_cohort_registry()


@router.get("/fairness-analytics/evidence/batch/{batch_id}", response_class=HTMLResponse)
async def evidence_fairness_batch_page(
    request: Request,
    batch_id: int,
    db: Session = Depends(get_db),
    fairness_epoch: str = "EVIDENCE_FAIRNESS_v1",
    metric_contract: str = "evidence_distribution_v1",
):
    from app.evidence_fairness_analytics import build_batch_evidence_fairness_report

    batch = _batch_or_404(db, batch_id)
    report = build_batch_evidence_fairness_report(
        db, batch_id, fairness_epoch=fairness_epoch, metric_contract=metric_contract
    )
    user = get_current_user(request, db)
    user_id = get_current_user_id(request)
    sub_info = get_subscription_info(db, user_id) if user_id else None
    templates = get_templates(request)
    return templates.TemplateResponse(
        "evidence_fairness_analytics.html",
        {
            "request": request,
            "user": user,
            "app_title": app_title(),
            "batch_id": batch_id,
            "batch": batch,
            "report": report,
            "subscription_info": sub_info,
        },
    )


@router.get("/fairness-analytics/distribution/batch/{batch_id}", response_class=HTMLResponse)
async def statistical_distribution_batch_page(
    request: Request, batch_id: int, db: Session = Depends(get_db)
):
    from app.statistical_distribution_analytics import build_batch_statistical_distribution_report

    batch = _batch_or_404(db, batch_id)
    report = build_batch_statistical_distribution_report(db, batch_id)
    sub_info = subscription_info_for_user(db, batch.user_id)
    templates = get_templates(request)
    return templates.TemplateResponse(
        "fairness_analytics_batch.html",
        {
            "request": request,
            "batch": batch,
            "page_title": "Statistical Distribution",
            "page_title_ar": "التوزيع الإحصائي",
            "report": report,
            "report_json": json.dumps(report, ensure_ascii=False),
            "subscription_info": sub_info,
        },
    )
