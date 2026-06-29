"""Appeal engine — submit, retrieve, independent examiner review."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.appeals.appeal_audit import log_appeal_event, read_appeal_audit
from app.appeals.appeal_case import (
    AppealCase,
    AppealStatus,
    load_appeal_case,
    list_appeals_for_submission,
    new_case_id,
    save_appeal_case,
)
from app.appeals.appeal_decision import record_appeal_decision
from app.appeals.evidence_rehydrator import rehydrate_appeal_evidence
from app.appeals.reviewer_assignment import assign_reviewer
from app.governance.examiner_mode import load_examiner_review
from app.governance.permissions import GovernanceRole, require_permission


def submit_appeal(
    *,
    submission_key: str,
    session_id: str,
    student_id: str,
    reason: str,
    student_statement: Optional[str] = None,
) -> Dict[str, Any]:
    """Student appeal — anchored to existing replay snapshot."""
    rehydrated = rehydrate_appeal_evidence(submission_key, session_id)
    if rehydrated.get("status") != "ok":
        return {
            "status": "rejected",
            "error": "replay_snapshot_required",
            "detail": "Appeals require an existing replay snapshot — no re-execution",
        }

    case = AppealCase(
        case_id=new_case_id(),
        submission_key=submission_key,
        session_id=session_id,
        student_id=student_id,
        reason=reason,
        student_statement=student_statement,
        replay_hash=rehydrated.get("deterministic_hash"),
        status=AppealStatus.REPLAY_AUDIT_REQUESTED,
    )
    save_appeal_case(case)

    log_appeal_event(
        case_id=case.case_id,
        actor=student_id,
        action="submit_appeal",
        replay_hash=case.replay_hash,
        metadata={"reason": reason},
    )

    return {
        "status": "submitted",
        "case": case.to_dict(),
        "replay_anchor": rehydrated.get("deterministic_hash"),
        "policy": "replay_snapshot_only",
    }


def get_appeal_status(case_id: str) -> Dict[str, Any]:
    case = load_appeal_case(case_id)
    if not case:
        return {"status": "not_found"}
    return {
        "status": "ok",
        "case": case.to_dict(),
        "audit_trail": read_appeal_audit(case_id),
    }


def review_appeal(
    case_id: str,
    *,
    actor: str,
    actor_role: GovernanceRole,
) -> Dict[str, Any]:
    """Independent examiner review — replay bundle, not LLM summary."""
    require_permission(actor_role, "resolve_appeal")
    case = load_appeal_case(case_id)
    if not case:
        return {"status": "not_found"}

    session_ref = f"{case.submission_key}/{case.session_id}"
    review = load_examiner_review(session_ref)
    rehydrated = rehydrate_appeal_evidence(case.submission_key, case.session_id)

    log_appeal_event(
        case_id=case_id,
        actor=actor,
        action="independent_review_started",
        replay_hash=case.replay_hash,
    )

    return {
        "status": "ok",
        "case": case.to_dict(),
        "examiner_review": review,
        "rehydrated_evidence": rehydrated,
    }


def resolve_appeal(
    case_id: str,
    *,
    actor: str,
    actor_role: GovernanceRole,
    decision: str,
    rationale: str,
    new_grade: Optional[str] = None,
    assign_to: Optional[str] = None,
) -> Dict[str, Any]:
    case = load_appeal_case(case_id)
    if not case:
        return {"status": "not_found"}

    if case.status == AppealStatus.SUBMITTED and assign_to:
        assign_reviewer(case, actor=actor, reviewer=assign_to)
        case = load_appeal_case(case_id)
        if not case:
            return {"status": "not_found"}

    return record_appeal_decision(
        case,
        actor=actor,
        actor_role=actor_role,
        decision=decision,
        rationale=rationale,
        new_grade=new_grade,
    )


def list_submission_appeals(submission_key: str) -> Dict[str, Any]:
    return {"submission_key": submission_key, "appeals": list_appeals_for_submission(submission_key)}
