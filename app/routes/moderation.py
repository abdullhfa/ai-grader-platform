"""Human labels moderation — teacher review UI (Institutional Closure Phase 1)."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

import json

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

from app.calibration.human_moderation_service import (
    apply_ai_hints_as_teacher_acceptance,
    get_record_detail,
    labels_path,
    list_records,
    save_teacher_review,
)
from app.routes.deps import app_title, get_templates

router = APIRouter(tags=["moderation"])


class CriterionInput(BaseModel):
    decision: Optional[str] = None
    confidence: Optional[float] = None
    notes: Optional[str] = None


class TeacherReviewInput(BaseModel):
    reviewer: str = Field(..., min_length=1)
    reviewed_at: Optional[str] = None
    overall_grade: Optional[str] = None
    overall_grade_notes: Optional[str] = None
    criteria: Optional[Dict[str, CriterionInput]] = None


class AcceptAiHintsInput(BaseModel):
    reviewer: str = Field(..., min_length=1)
    accept_overall: bool = True


@router.get("/institutional/moderation", response_class=HTMLResponse)
async def human_moderation_page(request: Request):
    return get_templates(request).TemplateResponse(
        "human_moderation.html",
        {
            "request": request,
            "app_title": app_title(),
            "labels_path": str(labels_path()),
        },
    )


@router.get("/api/institutional/moderation/progress")
async def moderation_progress_api(wave: Optional[str] = None):
    rows = list_records(wave=wave)
    complete = sum(1 for r in rows if r["complete"])
    return {
        "records": rows,
        "total": len(rows),
        "fully_complete": complete,
        "labels_path": str(labels_path()),
    }


@router.get("/api/institutional/moderation/{submission_id}")
async def moderation_record_api(submission_id: int):
    try:
        return get_record_detail(submission_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/institutional/moderation/{submission_id}")
async def moderation_save_api(submission_id: int, body: TeacherReviewInput):
    try:
        criteria = None
        if body.criteria:
            criteria = {k: v.model_dump(exclude_none=True) for k, v in body.criteria.items()}
        return save_teacher_review(
            submission_id,
            reviewer=body.reviewer,
            reviewed_at=body.reviewed_at,
            overall_grade=body.overall_grade,
            overall_grade_notes=body.overall_grade_notes,
            criteria=criteria,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.post("/api/institutional/moderation/{submission_id}/accept-ai-hints")
async def moderation_accept_ai_hints_api(submission_id: int, body: AcceptAiHintsInput):
    """Teacher explicitly accepts AI suggestions — not automated fabrication."""
    try:
        return apply_ai_hints_as_teacher_acceptance(
            submission_id,
            reviewer=body.reviewer,
            accept_overall=body.accept_overall,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/api/institutional/governance-calibration-cycle")
async def governance_calibration_cycle_api():
    from app.calibration.governance_calibration import build_from_closure_reports

    reports = Path(__file__).resolve().parents[1] / "calibration/reports/closure"
    if not (reports / "phase_a_disagreement.json").exists():
        raise HTTPException(status_code=404, detail="Run institutional closure first")
    return build_from_closure_reports(reports)


@router.get("/institutional/governance-review", response_class=HTMLResponse)
async def governance_review_page(request: Request):
    from app.calibration.governance_calibration import build_from_closure_reports

    reports = Path(__file__).resolve().parents[1] / "calibration/reports/closure"
    cycle = build_from_closure_reports(reports) if (reports / "phase_a_disagreement.json").exists() else {}
    intel_path = reports / "GOVERNANCE_INTELLIGENCE_REVIEW_v1.json"
    intel = json.loads(intel_path.read_text(encoding="utf-8")) if intel_path.exists() else {}
    return get_templates(request).TemplateResponse(
        "governance_calibration_review.html",
        {"request": request, "app_title": app_title(), "cycle": cycle, "intel": intel},
    )
