"""LMS / BTEC grade export — CSV first, JSON second."""
from __future__ import annotations

import csv
import io
import json
from pathlib import Path
from typing import Any, Dict, List, Optional


def _load_signoff(submission_key: str, session_id: str) -> Optional[Dict[str, Any]]:
    path = (
        Path("uploads/governance/signoffs")
        / submission_key.replace("/", "_")
        / f"{session_id}.json"
    )
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def build_lms_export_rows(
    records: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Normalize grading records for LMS CSV/JSON export."""
    rows = []
    for rec in records:
        # LMS is a final-award consumer.  Do not silently export a calculated
        # band from a draft/pending decision.
        decision = rec.get("governance_decision") or rec.get("governance_snapshot")
        if decision is not None:
            from app.governance_decision import require_final_award

            final_decision = require_final_award(decision)
            final_grade = final_decision.official_grade
        else:
            final_grade = None
        key = str(rec.get("submission_key") or rec.get("student_name") or "")
        session_id = str(rec.get("session_id") or "")
        signoff = _load_signoff(key, session_id) if session_id else None
        rows.append({
            "student_id": rec.get("student_id") or key,
            "student_name": rec.get("student_name") or key,
            "submission_key": key,
            "session_id": session_id,
            "grade_level": final_grade or (signoff or {}).get("final_grade") or rec.get("grade_level") or "",
            "percentage": rec.get("percentage") or "",
            "replay_hash": rec.get("replay_hash") or (signoff or {}).get("replay_hash") or "",
            "signed_evaluation_hash": (signoff or {}).get("signed_evaluation_hash") or "",
            "signoff_timestamp": (signoff or {}).get("timestamp") or "",
            "examiner_id": (signoff or {}).get("examiner_id") or "",
            "export_schema": "lms_grade_export_v1",
        })
    return rows


def export_lms_csv(records: List[Dict[str, Any]]) -> str:
    rows = build_lms_export_rows(records)
    if not rows:
        return "student_id,student_name,grade_level,percentage,replay_hash,signed_evaluation_hash\n"
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=list(rows[0].keys()), extrasaction="ignore")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def export_lms_json(records: List[Dict[str, Any]]) -> Dict[str, Any]:
    rows = build_lms_export_rows(records)
    return {
        "schema": "lms_grade_export_v1",
        "format": "json",
        "count": len(rows),
        "records": rows,
    }
