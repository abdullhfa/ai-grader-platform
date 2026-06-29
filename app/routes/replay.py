"""Replay and governance analytics API routes."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app import models
from app.auth import get_current_user, get_current_user_id
from app.database import get_db
from app.models import Submission
from app.routes.deps import app_title, get_templates, load_grading_snapshot
from app.services.subscription import get_subscription_info

router = APIRouter(tags=["replay"])


@router.get("/api/authority-replay/{submission_id}")
async def authority_replay_api(submission_id: int, db: Session = Depends(get_db)):
    from app.authority_replay import build_authority_replay

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    return build_authority_replay(load_grading_snapshot(submission))


@router.get("/api/timeline-replay/{submission_id}")
async def timeline_replay_api(submission_id: int, db: Session = Depends(get_db)):
    from app.academic_event_replay import build_academic_timeline_replay

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    snap = load_grading_snapshot(submission)
    graded_at = None
    if getattr(submission, "summary", None) and submission.summary.graded_at:
        graded_at = submission.summary.graded_at.isoformat() + "Z"
    return build_academic_timeline_replay(snap, graded_at=graded_at)


@router.get("/api/deterministic-replay/{submission_id}")
async def deterministic_replay_api(
    submission_id: int, db: Session = Depends(get_db), full: bool = False
):
    from app.deterministic_replay_engine import build_deterministic_replay

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    snap = load_grading_snapshot(submission)
    graded_at = None
    if getattr(submission, "summary", None) and submission.summary.graded_at:
        graded_at = submission.summary.graded_at.isoformat() + "Z"
    return build_deterministic_replay(snap, graded_at=graded_at, include_full_state=full)


@router.get("/api/governance-analytics/batch/{batch_id}")
async def governance_analytics_batch_api(batch_id: int, db: Session = Depends(get_db)):
    from app.governance_analytics import build_batch_governance_analytics

    batch = db.query(models.BatchGrading).filter(models.BatchGrading.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return build_batch_governance_analytics(db, batch_id)


@router.get("/api/policy-comparison/batch/{batch_id}")
async def policy_comparison_batch_api(batch_id: int, db: Session = Depends(get_db)):
    from app.policy_comparison_report import build_batch_policy_comparison_report

    batch = db.query(models.BatchGrading).filter(models.BatchGrading.id == batch_id).first()
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    return build_batch_policy_comparison_report(db, batch_id)


@router.post("/api/governance-drift-replay/{submission_id}")
async def governance_drift_replay_api(
    submission_id: int, request: Request, db: Session = Depends(get_db)
):
    from app.counterfactual_replay import detect_governance_drift

    submission = db.query(Submission).filter(Submission.id == submission_id).first()
    if not submission:
        raise HTTPException(status_code=404, detail="Submission not found")
    body = {}
    try:
        body = await request.json()
    except Exception:
        pass
    snap = load_grading_snapshot(submission)
    if not snap:
        raise HTTPException(status_code=400, detail="No grading snapshot")
    events = (snap.get("academic_event_log") or {}).get("events") or []
    return detect_governance_drift(
        events,
        baseline_contract=str(body.get("baseline_contract") or "2.1"),
        comparison_contract=str(body.get("comparison_contract") or "2.2"),
        sandbox_context={"evidence_lineage": snap.get("evidence_lineage") or {}},
    )


@router.get("/api/governance-contracts")
async def governance_contracts_api():
    from app.governance_contract_registry import list_contracts

    return list_contracts()


@router.get("/api/governance/freeze-registry")
async def governance_freeze_registry_api():
    from app.governance_freeze_registry import build_freeze_registry_report

    return build_freeze_registry_report()
