"""Institutional governance API — examiner mode, sign-off, appeals."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.auth import get_current_user
from app.database import get_db
from app.governance.audit_log import read_audit_log
from app.governance.examiner_mode import (
    escalate_review,
    load_examiner_review,
    parse_session_ref,
    start_examiner_review,
)
from app.governance.institutional_export import (
    build_replay_package_zip,
    export_evidence_json,
    export_signed_report_stub,
)
from app.governance.override_engine import apply_grade_override
from app.governance.permissions import GovernanceRole, resolve_governance_role
from app.governance.review_session import load_review_session
from app.governance.signoff import apply_signoff
from app.appeals.appeal_engine import (
    get_appeal_status,
    list_submission_appeals,
    resolve_appeal,
    review_appeal,
    submit_appeal,
)

router = APIRouter(prefix="/api/governance", tags=["governance"])


class ActorBody(BaseModel):
    actor: str = Field(..., min_length=1)
    actor_role: Optional[str] = None


class OverrideBody(ActorBody):
    session_ref: str
    previous_grade: str
    new_grade: str
    reason: str = Field(..., min_length=3)
    criterion_id: Optional[str] = None


class SignoffBody(ActorBody):
    session_ref: str
    final_grade: str
    reason: Optional[str] = None


class EscalateBody(ActorBody):
    session_ref: str
    reason: str = Field(..., min_length=3)
    target_role: str = "senior_examiner"


class AppealSubmitBody(BaseModel):
    submission_key: str
    session_id: str
    student_id: str
    reason: str = Field(..., min_length=3)
    student_statement: Optional[str] = None


class AppealResolveBody(ActorBody):
    decision: str
    rationale: str = Field(..., min_length=3)
    new_grade: Optional[str] = None
    assign_to: Optional[str] = None


def _role(request: Request, declared: Optional[str], db: Session) -> GovernanceRole:
    user = get_current_user(request, db)
    return resolve_governance_role(user, declared_role=declared, db=db)


def _permission_error(exc: PermissionError) -> HTTPException:
    return HTTPException(status_code=403, detail=str(exc))


def _security_log(request: Request, action: str, resource: str, outcome: str = "allowed") -> None:
    try:
        from app.ops.correlation import get_correlation
        from app.security.security_audit import log_security_action

        actor = request.client.host if request.client else "unknown"
        ctx = get_correlation()
        log_security_action(
            action=action,
            actor=actor,
            resource=resource,
            outcome=outcome,
            trace_id=ctx.trace_id if ctx else None,
            ip_address=actor,
        )
    except Exception:
        pass


@router.get("/review/{session_ref:path}")
async def governance_review_api(
    session_ref: str, request: Request, db: Session = Depends(get_db)
):
    """Load replay inspection bundle for examiner — replay-first review."""
    try:
        role = _role(request, None, db)
        if role == GovernanceRole.STUDENT:
            raise HTTPException(status_code=403, detail="Examiner access required")
        _security_log(request, "replay_access", session_ref)
        return load_examiner_review(session_ref)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/review/{session_ref:path}/start")
async def governance_start_review_api(
    session_ref: str, body: ActorBody, request: Request, db: Session = Depends(get_db)
):
    try:
        role = _role(request, body.actor_role, db)
        return start_examiner_review(session_ref, actor=body.actor, actor_role=role)
    except PermissionError as exc:
        raise _permission_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/override")
async def governance_override_api(
    body: OverrideBody, request: Request, db: Session = Depends(get_db)
):
    try:
        role = _role(request, body.actor_role, db)
        submission_key, session_id = parse_session_ref(body.session_ref)
        session = load_review_session(submission_key, session_id)
        if not session:
            from app.governance.review_session import get_or_create_review_session

            bundle = load_examiner_review(body.session_ref)
            session = get_or_create_review_session(
                submission_key,
                session_id,
                replay_hash=(bundle.get("replay_bundle") or {}).get("deterministic_hash"),
            )
        return apply_grade_override(
            session,
            actor=body.actor,
            actor_role=role,
            previous_grade=body.previous_grade,
            new_grade=body.new_grade,
            reason=body.reason,
            criterion_id=body.criterion_id,
            replay_hash=session.replay_hash,
        )
    except PermissionError as exc:
        raise _permission_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/signoff")
async def governance_signoff_api(
    body: SignoffBody, request: Request, db: Session = Depends(get_db)
):
    try:
        role = _role(request, body.actor_role, db)
        submission_key, session_id = parse_session_ref(body.session_ref)
        session = load_review_session(submission_key, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Review session not found — start review first")
        bundle = load_examiner_review(body.session_ref)
        replay_hash = (bundle.get("replay_bundle") or {}).get("deterministic_hash")
        if not replay_hash:
            raise HTTPException(status_code=422, detail="Replay hash required for sign-off")
        return apply_signoff(
            session,
            actor=body.actor,
            actor_role=role,
            final_grade=body.final_grade,
            replay_hash=replay_hash,
            reason=body.reason,
        )
    except PermissionError as exc:
        raise _permission_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.post("/escalate")
async def governance_escalate_api(
    body: EscalateBody, request: Request, db: Session = Depends(get_db)
):
    try:
        role = _role(request, body.actor_role, db)
        submission_key, session_id = parse_session_ref(body.session_ref)
        session = load_review_session(submission_key, session_id)
        if not session:
            raise HTTPException(status_code=404, detail="Review session not found")
        return escalate_review(
            session,
            actor=body.actor,
            actor_role=role,
            reason=body.reason,
            target_role=body.target_role,
        )
    except PermissionError as exc:
        raise _permission_error(exc)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/audit-log/{session_ref:path}")
async def governance_audit_log_api(
    session_ref: str, request: Request, db: Session = Depends(get_db)
):
    try:
        role = _role(request, None, db)
        if role == GovernanceRole.STUDENT:
            raise HTTPException(status_code=403, detail="Audit access denied")
        _, session_id = parse_session_ref(session_ref)
        return {"session_ref": session_ref, "events": read_audit_log(session_id)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/export/{session_ref:path}/evidence.json")
async def governance_export_evidence_api(session_ref: str, request: Request):
    try:
        submission_key, session_id = parse_session_ref(session_ref)
        return export_evidence_json(submission_key, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/export/{session_ref:path}/replay.zip")
async def governance_export_replay_zip_api(session_ref: str, request: Request):
    try:
        submission_key, session_id = parse_session_ref(session_ref)
        _security_log(request, "export_replay_zip", session_ref)
        data = build_replay_package_zip(submission_key, session_id)
        filename = f"replay_{submission_key}_{session_id}.zip".replace("/", "_")
        return Response(
            content=data,
            media_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/export/{session_ref:path}/signed-report.json")
async def governance_export_signed_report_api(session_ref: str):
    try:
        submission_key, session_id = parse_session_ref(session_ref)
        return export_signed_report_stub(submission_key, session_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/export/{session_ref:path}/signed-report.pdf")
async def governance_export_signed_pdf_api(session_ref: str):
    try:
        from app.governance.signed_pdf_report import build_signed_pdf_report

        submission_key, session_id = parse_session_ref(session_ref)
        pdf_bytes = build_signed_pdf_report(submission_key, session_id)
        filename = f"signed_report_{submission_key}_{session_id}.pdf".replace("/", "_")
        return Response(
            content=pdf_bytes,
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


@router.get("/schemas")
async def governance_schemas_api():
    from app.governance.schema_contracts import list_contract_schemas

    return {"schemas": list_contract_schemas(), "directory": "schemas/"}


@router.post("/export/lms.csv")
async def governance_lms_csv_api(records: List[Dict[str, Any]]):
    from app.governance.lms_export import export_lms_csv

    csv_text = export_lms_csv(records)
    return Response(content=csv_text, media_type="text/csv")


@router.post("/export/lms.json")
async def governance_lms_json_api(records: List[Dict[str, Any]]):
    from app.governance.lms_export import export_lms_json

    return export_lms_json(records)


# --- Appeals (governance-adjacent, replay-backed) ---

appeals_router = APIRouter(prefix="/api/appeals", tags=["appeals"])


@appeals_router.post("/submit")
async def appeals_submit_api(body: AppealSubmitBody):
    return submit_appeal(
        submission_key=body.submission_key,
        session_id=body.session_id,
        student_id=body.student_id,
        reason=body.reason,
        student_statement=body.student_statement,
    )


@appeals_router.get("/{case_id}")
async def appeals_status_api(case_id: str):
    result = get_appeal_status(case_id)
    if result.get("status") == "not_found":
        raise HTTPException(status_code=404, detail="Appeal case not found")
    return result


@appeals_router.get("/submission/{submission_key}")
async def appeals_list_api(submission_key: str):
    return list_submission_appeals(submission_key)


@appeals_router.post("/{case_id}/review")
async def appeals_review_api(
    case_id: str, body: ActorBody, request: Request, db: Session = Depends(get_db)
):
    role = _role(request, body.actor_role, db)
    try:
        return review_appeal(case_id, actor=body.actor, actor_role=role)
    except PermissionError as exc:
        raise _permission_error(exc)


@appeals_router.post("/{case_id}/resolve")
async def appeals_resolve_api(
    case_id: str, body: AppealResolveBody, request: Request, db: Session = Depends(get_db)
):
    role = _role(request, body.actor_role, db)
    try:
        return resolve_appeal(
            case_id,
            actor=body.actor,
            actor_role=role,
            decision=body.decision,
            rationale=body.rationale,
            new_grade=body.new_grade,
            assign_to=body.assign_to,
        )
    except PermissionError as exc:
        raise _permission_error(exc)
