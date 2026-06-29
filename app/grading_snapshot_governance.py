"""
Grading Snapshot Governance — canonical state semantics for replay integrity.

Evidence identity precedes interpretation: replay is allowed only for
governance-compatible canonical snapshots, not arbitrary AI outputs.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

FREEZE_VERSION = "GOVERNANCE_FREEZE_v1"
REPLAY_VERSION = "v1"
TAXONOMY_DRIFT_MODE = "GFM_CANONICAL_DRIFT"


def build_grading_governance_block(
    *,
    grading_hash: str,
    grade_level: str = "",
    percentage: float = 0.0,
    governance_state: str = "approved",
    institutional_status: str = "canonical",
    drift_status: str = "clean",
    reviewer_override: bool = False,
    replay_version: str = REPLAY_VERSION,
    supersession: Optional[Dict[str, Any]] = None,
    replay_cache_generation: Optional[int] = None,
) -> Dict[str, Any]:
    block: Dict[str, Any] = {
        "grading_hash": grading_hash or "",
        "governance_state": governance_state,
        "replay_version": replay_version,
        "freeze_version": FREEZE_VERSION,
        "drift_status": drift_status,
        "reviewer_override": (reviewer_override),
        "institutional_status": institutional_status,
        "grade_level_at_snapshot": grade_level or "",
        "percentage_at_snapshot": percentage,
    }
    if replay_cache_generation is not None:
        block["replay_cache_generation"] = (replay_cache_generation)
    if supersession:
        block["supersession"] = supersession
    return block


def parse_snapshot_governance(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not snapshot:
        return {}
    gov = snapshot.get("grading_governance")
    if isinstance(gov, dict):
        return gov
    return {}


def is_canonical_replay_eligible(snapshot: Optional[Dict[str, Any]]) -> bool:
    """Cache replay only when a governance-clean canonical snapshot exists."""
    gov = parse_snapshot_governance(snapshot)
    if not gov.get("grading_hash"):
        return False
    if gov.get("institutional_status") == "superseded":
        return False
    if gov.get("governance_state") not in ("approved", "canonical"):
        return False
    if gov.get("drift_status") in ("canonical_drift_detected", "unresolved"):
        return False
    return True


def attach_governance_to_payload(
    payload: Dict[str, Any],
    *,
    grading_hash: str,
    grade_level: str = "",
    percentage: float = 0.0,
    governance_state: str = "approved",
    institutional_status: str = "canonical",
) -> Dict[str, Any]:
    from app.submission_replay_cache import current_replay_cache_generation

    out = dict(payload)
    out["grading_governance"] = build_grading_governance_block(
        grading_hash=grading_hash,
        grade_level=grade_level or str(out.get("grade_level") or ""),
        percentage=float(percentage or out.get("percentage") or 0),
        governance_state=governance_state,
        institutional_status=institutional_status,
        replay_cache_generation=current_replay_cache_generation(),
    )
    return out


def detect_canonical_drift(
    *,
    grading_hash: str,
    new_grade: str,
    new_percentage: float,
    prior_records: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """
    identical evidence (grading_hash) → divergent institutional outcomes.
    Returns drift incident dict or None.
    """
    if not grading_hash:
        return None

    canonical_prior: Optional[Dict[str, Any]] = None
    for rec in prior_records:
        if rec.get("grading_hash") != grading_hash:
            continue
        if rec.get("institutional_status") == "superseded":
            continue
        canonical_prior = rec
        break

    if not canonical_prior:
        return None

    prior_grade = str(canonical_prior.get("grade_level") or "")
    prior_pct = float(canonical_prior.get("percentage") or 0)
    new_grade_s = (new_grade or "")
    if prior_grade == new_grade_s:
        return None
    if not prior_grade or not new_grade_s:
        return None

    return {
        "failure_mode_id": TAXONOMY_DRIFT_MODE,
        "grading_hash": grading_hash,
        "canonical_submission_id": canonical_prior.get("submission_id"),
        "canonical_batch_id": canonical_prior.get("batch_id"),
        "canonical_grade": prior_grade,
        "canonical_percentage": prior_pct,
        "divergent_submission_id": None,
        "divergent_batch_id": None,
        "divergent_grade": new_grade,
        "divergent_percentage": new_percentage,
        "reason_ar": (
            "نفس دليل التسليم (grading_hash متطابق) أنتج نتيجة مؤسسية مختلفة — "
            "grading variance وليس تغيّر evidence."
        ),
        "resolution": "institutional_supersession",
    }


def build_supersession_record(
    *,
    canonical_submission_id: int,
    canonical_batch_id: int,
    grading_hash: str,
    drift_incident: Dict[str, Any],
) -> Dict[str, Any]:
    return {
        "superseded_by_canonical_snapshot": True,
        "canonical_submission_id": canonical_submission_id,
        "canonical_batch_id": canonical_batch_id,
        "grading_hash": grading_hash,
        "drift_failure_mode": TAXONOMY_DRIFT_MODE,
        "reason_ar": drift_incident.get("reason_ar", ""),
        "canonical_grade": drift_incident.get("canonical_grade"),
        "superseded_grade": drift_incident.get("divergent_grade"),
        "explanation_ar": (
            "هذه النتيجة مُعلّمة superseded — المرجع المؤسسي هو أول snapshot "
            "governance-compatible لنفس الملف."
        ),
    }


def mark_snapshot_superseded(
    snapshot: Dict[str, Any],
    *,
    supersession: Dict[str, Any],
) -> Dict[str, Any]:
    out = dict(snapshot)
    gov = parse_snapshot_governance(out)
    gov.update(
        {
            "institutional_status": "superseded",
            "governance_state": "superseded",
            "drift_status": "canonical_drift_detected",
            "supersession": supersession,
        }
    )
    out["grading_governance"] = gov
    out["governance_incidents"] = list(out.get("governance_incidents") or []) + [
        {
            "failure_mode_id": TAXONOMY_DRIFT_MODE,
            **supersession,
        }
    ]
    return out


def load_submission_governance_record(
    submission: Any,
    summary: Any = None,
) -> Dict[str, Any]:
    snap: Dict[str, Any] = {}
    if getattr(submission, "grading_snapshot_json", None):
        try:
            snap = json.loads(str(submission.grading_snapshot_json))
        except Exception:
            snap = {}
    gov = parse_snapshot_governance(snap)
    grading_hash = gov.get("grading_hash") or snap.get("grading_hash") or ""
    grade_level = (
        (summary.grade_level if summary else None)
        or gov.get("grade_level_at_snapshot")
        or snap.get("grade_level")
        or ""
    )
    percentage = float(
        (summary.percentage if summary else 0)
        or gov.get("percentage_at_snapshot")
        or snap.get("percentage")
        or 0
    )
    return {
        "submission_id": getattr(submission, "id", None),
        "batch_id": getattr(submission, "batch_id", None),
        "student_name": getattr(submission, "student_name", ""),
        "grading_hash": grading_hash,
        "grade_level": grade_level,
        "percentage": percentage,
        "institutional_status": gov.get("institutional_status", "canonical"),
        "governance_state": gov.get("governance_state", "approved"),
        "drift_status": gov.get("drift_status", "clean"),
        "snapshot": snap,
    }


def submission_replay_eligible(submission: Any, summary: Any = None) -> bool:
    """Whether an existing submission may be replayed as institutional canonical state."""
    from app.submission_replay_cache import submission_replay_cache_valid

    if not submission_replay_cache_valid(submission):
        return False
    rec = load_submission_governance_record(submission, summary)
    snap = rec.get("snapshot") or {}
    gov = parse_snapshot_governance(snap)
    if gov:
        return is_canonical_replay_eligible(snap)
    from app.archive_extraction_utils import hash_submission_file

    return bool(
        hash_submission_file(str(getattr(submission, "submission_file_path", "") or ""), "")
    )


def apply_institutional_supersession(
    db: Any,
    *,
    superseded_submission_id: int,
    canonical_submission_id: int,
    drift_incident: Dict[str, Any],
) -> bool:
    """
    Mark divergent submission superseded; align displayed grades with canonical snapshot.
    Preserves both rows for audit — no silent delete.
    """
    from app.models import GradingResult, GradingSummary, Submission

    superseded = (
        db.query(Submission).filter(Submission.id == superseded_submission_id).first()
    )
    canonical = (
        db.query(Submission).filter(Submission.id == canonical_submission_id).first()
    )
    if not superseded or not canonical:
        return False

    can_summary = (
        db.query(GradingSummary)
        .filter(GradingSummary.submission_id == canonical_submission_id)
        .first()
    )
    if not can_summary:
        return False

    snap: Dict[str, Any] = {}
    if superseded.grading_snapshot_json:
        try:
            snap = json.loads(str(superseded.grading_snapshot_json))
        except Exception:
            snap = {}

    supersession = build_supersession_record(
        canonical_submission_id=canonical_submission_id,
        canonical_batch_id=int(getattr(canonical, "batch_id", 0) or 0),
        grading_hash=str(drift_incident.get("grading_hash") or ""),
        drift_incident=drift_incident,
    )
    snap = mark_snapshot_superseded(snap, supersession=supersession)
    superseded.grading_snapshot_json = json.dumps(snap, ensure_ascii=False)

    sup_summary = (
        db.query(GradingSummary)
        .filter(GradingSummary.submission_id == superseded_submission_id)
        .first()
    )
    if sup_summary:
        sup_summary.total_score = can_summary.total_score
        sup_summary.max_score = can_summary.max_score
        sup_summary.percentage = can_summary.percentage
        sup_summary.grade_level = can_summary.grade_level
        sup_summary.overall_feedback = can_summary.overall_feedback
        sup_summary.strengths = can_summary.strengths
        sup_summary.improvements = can_summary.improvements

    db.query(GradingResult).filter(
        GradingResult.submission_id == superseded_submission_id
    ).delete(synchronize_session=False)
    for src in (
        db.query(GradingResult)
        .filter(GradingResult.submission_id == canonical_submission_id)
        .all()
    ):
        db.add(
            GradingResult(
                submission_id=superseded_submission_id,
                criteria_id=src.criteria_id,
                achieved=src.achieved,
                score=src.score,
                max_score=src.max_score,
                missing_points=src.missing_points,
                feedback=src.feedback,
                next_level_requirements=src.next_level_requirements,
            )
        )

    db.commit()
    print(
        f"🏛️ [SUPERSESSION] submission #{superseded_submission_id} "
        f"→ canonical #{canonical_submission_id} ({drift_incident.get('canonical_grade')})"
    )
    return True


def reconcile_canonical_drift_for_assignment(db: Any, assignment_id: int) -> List[Dict[str, Any]]:
    """Detect and supersede canonical drift across all completed submissions."""
    from app.archive_extraction_utils import hash_submission_file
    from app.models import GradingSummary, Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(
            Submission.assignment_id == assignment_id,
            Submission.status == SubmissionStatus.COMPLETED,
        )
        .order_by(Submission.id.asc())
        .all()
    )

    incidents: List[Dict[str, Any]] = []
    prior_records: List[Dict[str, Any]] = []

    for sub in subs:
        summary = (
            db.query(GradingSummary).filter(GradingSummary.submission_id == sub.id).first()
        )
        rec = load_submission_governance_record(sub, summary)
        if not rec.get("grading_hash"):
            rec["grading_hash"] = hash_submission_file(
                str(sub.submission_file_path or ""), ""
            )

        drift = detect_canonical_drift(
            grading_hash=str(rec.get("grading_hash") or ""),
            new_grade=str(rec.get("grade_level") or ""),
            new_percentage=float(rec.get("percentage") or 0),
            prior_records=prior_records,
        )
        if drift:
            drift["divergent_submission_id"] = sub.id
            drift["divergent_batch_id"] = sub.batch_id
            canonical_id = drift.get("canonical_submission_id")
            if canonical_id:
                apply_institutional_supersession(
                    db,
                    superseded_submission_id=sub.id,
                    canonical_submission_id=int(canonical_id),
                    drift_incident=drift,
                )
            incidents.append(drift)

        if rec.get("institutional_status") != "superseded":
            prior_records.append(rec)

    return incidents


def restore_summary_from_snapshot(db: Any, submission: Any) -> bool:
    """Restore displayed grades from snapshot payload when governance overwrote them."""
    from app.models import GradingSummary

    if not submission or not submission.grading_snapshot_json:
        return False
    try:
        snap = json.loads(str(submission.grading_snapshot_json))
    except Exception:
        return False
    if not snap.get("percentage") and not snap.get("grade_level"):
        return False

    summary = (
        db.query(GradingSummary)
        .filter(GradingSummary.submission_id == submission.id)
        .first()
    )
    if not summary:
        return False

    summary.total_score = int(snap.get("total_score") or summary.total_score or 0)
    summary.max_score = int(snap.get("max_score") or summary.max_score or 100)
    summary.percentage = float(snap.get("percentage") or summary.percentage or 0)
    summary.grade_level = str(snap.get("grade_level") or summary.grade_level or "U")
    if snap.get("overall_feedback"):
        summary.overall_feedback = snap.get("overall_feedback")
    if snap.get("strengths"):
        summary.strengths = json.dumps(snap.get("strengths"), ensure_ascii=False)
    if snap.get("improvements"):
        summary.improvements = json.dumps(snap.get("improvements"), ensure_ascii=False)

    gov = parse_snapshot_governance(snap)
    gov.update(
        {
            "institutional_status": "canonical",
            "governance_state": "approved",
            "drift_status": "none",
            "supersession": None,
        }
    )
    snap["grading_governance"] = gov
    submission.grading_snapshot_json = json.dumps(snap, ensure_ascii=False)
    return True
