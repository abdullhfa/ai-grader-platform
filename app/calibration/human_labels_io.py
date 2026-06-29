"""Load human_labels_v1 and convert to gold records for calibration."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def load_human_labels(path: Path) -> Dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _decision_to_achieved(decision: Any) -> Optional[bool]:
    if decision is None:
        return None
    text = str(decision).strip().lower()
    if text in ("achieved", "pass", "yes", "true", "1"):
        return True
    if text in ("not achieved", "not_achieved", "fail", "no", "false", "0"):
        return False
    return None


def human_labels_to_gold_records(labels_doc: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Convert human_labels_v1 records → unity_calibration gold rows."""
    rows: List[Dict[str, Any]] = []
    for rec in labels_doc.get("records") or []:
        sid = str(rec.get("submission_id") or "")
        criteria = rec.get("criteria") or {}
        if isinstance(criteria, dict):
            for crit_key, crit_row in criteria.items():
                if not isinstance(crit_row, dict):
                    continue
                achieved = _decision_to_achieved(crit_row.get("decision"))
                if achieved is None:
                    continue
                rows.append(
                    {
                        "submission_id": sid,
                        "criterion": str(crit_key),
                        "teacher_result": {
                            "achieved": achieved,
                            "confidence": crit_row.get("confidence"),
                        },
                        "teacher_notes": [crit_row.get("notes")] if crit_row.get("notes") else [],
                        "reviewer": rec.get("reviewer"),
                        "student": rec.get("student"),
                        "overall_grade_teacher": rec.get("overall_grade"),
                    }
                )
    return rows


def export_gold_from_human_labels(
    labels_path: Path,
    out_path: Path,
) -> Dict[str, Any]:
    doc = load_human_labels(labels_path)
    records = human_labels_to_gold_records(doc)
    out = {
        "schema": "human_labels_gold_export_v1",
        "source": str(labels_path),
        "record_count": len(records),
        "records": records,
    }
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    return out


def export_system_snapshots_from_db(
    submission_ids: Optional[List[int]] = None,
    out_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Export grading snapshots from DB for calibration."""
    import json as _json

    from app.database import SessionLocal
    from app.models import Submission

    db = SessionLocal()
    submissions: Dict[str, Any] = {}
    try:
        q = db.query(Submission).filter(Submission.grading_snapshot_json.isnot(None))
        if submission_ids:
            q = q.filter(Submission.id.in_(submission_ids))
        for sub in q.all():
            try:
                snap = _json.loads(str(sub.grading_snapshot_json))
            except (_json.JSONDecodeError, TypeError):
                continue
            if not isinstance(snap, dict):
                continue
            submissions[str(sub.id)] = snap
    finally:
        db.close()

    doc = {
        "schema": "system_snapshots_db_export_v1",
        "submission_count": len(submissions),
        "submissions": submissions,
    }
    if out_path:
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return doc


_CRITERIA_KEYS = ("P3", "P4", "P5", "P6", "P7", "M2", "M3", "D2", "D3")


def _ai_achieved_hint(snapshot: Dict[str, Any], crit_key: str) -> Optional[bool]:
    from app.calibration.taxonomy_helpers import criteria_match

    for cr in snapshot.get("criteria_results") or []:
        if isinstance(cr, dict) and criteria_match(str(cr.get("criteria_level") or ""), crit_key):
            return bool(cr.get("achieved"))
    return None


def seed_human_label_records(
    labels_path: Path,
    *,
    batch_id: Optional[int] = None,
    submission_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    """
    Ensure human_labels_v1 has PENDING records for DB submissions.
    Adds ai_system_achieved hints only — never fabricates teacher decisions.
    """
    import json as _json

    from app.database import SessionLocal
    from app.models import Submission

    doc = load_human_labels(labels_path) if labels_path.exists() else {
        "schema": "human_labels_v1",
        "description_ar": "مراجع بشري — املأ decision و overall_grade قبل calibration",
        "records": [],
    }
    existing = {int(r.get("submission_id") or 0) for r in doc.get("records") or []}

    db = SessionLocal()
    try:
        q = db.query(Submission).filter(Submission.grading_snapshot_json.isnot(None))
        if submission_ids:
            q = q.filter(Submission.id.in_(submission_ids))
        elif batch_id is not None:
            q = q.filter(Submission.batch_id == batch_id)
        subs = q.order_by(Submission.id).all()

        for sub in subs:
            sid = int(sub.id)
            if sid in existing:
                continue
            try:
                snap = _json.loads(str(sub.grading_snapshot_json))
            except (_json.JSONDecodeError, TypeError):
                snap = {}
            criteria: Dict[str, Any] = {}
            for key in _CRITERIA_KEYS:
                ai_hint = _ai_achieved_hint(snap, key) if snap else None
                criteria[key] = {
                    "decision": None,
                    "confidence": None,
                    "notes": "PENDING_REVIEW — يُعبّأ من المعلّم",
                    "ai_system_achieved": ai_hint,
                }
            doc.setdefault("records", []).append(
                {
                    "submission_id": sid,
                    "student": sub.student_name,
                    "student_name_ar": sub.student_name,
                    "batch_id": sub.batch_id,
                    "platform": "unknown",
                    "reviewer": None,
                    "reviewed_at": None,
                    "overall_grade": None,
                    "overall_grade_notes": "PENDING_REVIEW — يُعبّأ من المعلّم",
                    "ai_system_grade_level": snap.get("grade_level") if snap else None,
                    "criteria": criteria,
                }
            )
    finally:
        db.close()

    labels_path.parent.mkdir(parents=True, exist_ok=True)
    labels_path.write_text(_json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"record_count": len(doc.get("records") or []), "path": str(labels_path)}
