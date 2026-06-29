"""Human moderation — load/save human_labels_v1 (teacher decisions only)."""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.calibration.human_labels_io import load_human_labels

CRITERIA_KEYS = ("P3", "P4", "P5", "P6", "P7", "M2", "M3", "D2", "D3")

ROOT = Path(__file__).resolve().parents[2]
LABELS_PATH = ROOT / "app/calibration/human_labels_v1.json"

PRIORITY_WAVE_1 = [1]
PRIORITY_WAVE_2 = [22, 15, 19, 14, 16]
PRIORITY_WAVE_3 = [20, 21, 17, 18, 25]


def labels_path() -> Path:
    return LABELS_PATH


def _save_doc(doc: Dict[str, Any]) -> None:
    LABELS_PATH.parent.mkdir(parents=True, exist_ok=True)
    LABELS_PATH.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")


def find_record(doc: Dict[str, Any], submission_id: int) -> Optional[Dict[str, Any]]:
    for rec in doc.get("records") or []:
        if int(rec.get("submission_id") or 0) == submission_id:
            return rec
    return None


def record_progress(rec: Dict[str, Any]) -> Dict[str, Any]:
    crit = rec.get("criteria") or {}
    filled = sum(1 for k in CRITERIA_KEYS if (crit.get(k) or {}).get("decision") is not None)
    overall = rec.get("overall_grade") is not None
    total = len(CRITERIA_KEYS) + 1
    done = filled + (1 if overall else 0)
    return {
        "submission_id": rec.get("submission_id"),
        "student": rec.get("student_name_ar") or rec.get("student"),
        "criteria_filled": filled,
        "overall_filled": overall,
        "complete": filled == len(CRITERIA_KEYS) and overall,
        "pct": round(done / total * 100, 1),
    }


def list_records(*, wave: Optional[str] = None) -> List[Dict[str, Any]]:
    doc = load_human_labels(LABELS_PATH)
    rows = [record_progress(r) for r in doc.get("records") or []]
    if wave == "1":
        ids = set(PRIORITY_WAVE_1)
    elif wave == "2":
        ids = set(PRIORITY_WAVE_2)
    elif wave == "3":
        ids = set(PRIORITY_WAVE_3)
    else:
        return rows
    order = {sid: i for i, sid in enumerate(ids)}
    filtered = [r for r in rows if r["submission_id"] in ids]
    filtered.sort(key=lambda r: order.get(r["submission_id"], 999))
    return filtered


def get_record_detail(submission_id: int) -> Dict[str, Any]:
    doc = load_human_labels(LABELS_PATH)
    rec = find_record(doc, submission_id)
    if not rec:
        raise ValueError(f"submission {submission_id} not in human_labels_v1")
    crit_rows: List[Dict[str, Any]] = []
    for key in CRITERIA_KEYS:
        row = dict((rec.get("criteria") or {}).get(key) or {})
        ai = row.get("ai_system_achieved")
        crit_rows.append(
            {
                "criterion": key,
                "decision": row.get("decision"),
                "confidence": row.get("confidence"),
                "notes": row.get("notes"),
                "ai_system_achieved": ai,
            }
        )
    return {
        "submission_id": submission_id,
        "student": rec.get("student_name_ar") or rec.get("student"),
        "batch_id": rec.get("batch_id"),
        "platform": rec.get("platform"),
        "reviewer": rec.get("reviewer"),
        "reviewed_at": rec.get("reviewed_at"),
        "overall_grade": rec.get("overall_grade"),
        "overall_grade_notes": rec.get("overall_grade_notes"),
        "ai_system_grade_level": rec.get("ai_system_grade_level"),
        "criteria": crit_rows,
        "progress": record_progress(rec),
    }


def save_teacher_review(
    submission_id: int,
    *,
    reviewer: str,
    reviewed_at: Optional[str] = None,
    overall_grade: Optional[str] = None,
    overall_grade_notes: Optional[str] = None,
    criteria: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    doc = load_human_labels(LABELS_PATH)
    rec = find_record(doc, submission_id)
    if not rec:
        raise ValueError(f"submission {submission_id} not in human_labels_v1")

    rec["reviewer"] = reviewer.strip() or rec.get("reviewer")
    rec["reviewed_at"] = reviewed_at or rec.get("reviewed_at") or date.today().isoformat()
    if overall_grade is not None:
        rec["overall_grade"] = overall_grade.strip().upper() if overall_grade else None
    if overall_grade_notes is not None:
        rec["overall_grade_notes"] = overall_grade_notes

    if criteria:
        rec.setdefault("criteria", {})
        for key, payload in criteria.items():
            if key not in CRITERIA_KEYS or not isinstance(payload, dict):
                continue
            row = rec["criteria"].setdefault(key, {})
            decision = payload.get("decision")
            if decision is not None:
                text = str(decision).strip()
                if text.lower() in ("achieved", "not achieved", "not_achieved"):
                    row["decision"] = "Achieved" if text.lower() == "achieved" else "Not Achieved"
                elif text in ("Achieved", "Not Achieved"):
                    row["decision"] = text
            if payload.get("confidence") is not None:
                row["confidence"] = payload.get("confidence")
            if payload.get("notes") is not None:
                row["notes"] = payload.get("notes")

    _save_doc(doc)
    return {"ok": True, "submission_id": submission_id, "progress": record_progress(rec)}


def apply_ai_hints_as_teacher_acceptance(
    submission_id: int,
    *,
    reviewer: str,
    accept_overall: bool = True,
) -> Dict[str, Any]:
    """
    Teacher explicitly accepts AI hints — copies ai_system_achieved → decision.
    Not auto-run; requires authenticated teacher action via UI.
    """
    doc = load_human_labels(LABELS_PATH)
    rec = find_record(doc, submission_id)
    if not rec:
        raise ValueError(f"submission {submission_id} not in human_labels_v1")

    crit = rec.setdefault("criteria", {})
    applied = 0
    for key in CRITERIA_KEYS:
        row = crit.setdefault(key, {})
        if row.get("decision") is not None:
            continue
        hint = row.get("ai_system_achieved")
        if hint is None:
            continue
        row["decision"] = "Achieved" if hint else "Not Achieved"
        row["notes"] = "Teacher accepted AI hint via moderation UI"
        applied += 1

    rec["reviewer"] = reviewer.strip()
    rec["reviewed_at"] = date.today().isoformat()
    if accept_overall and rec.get("overall_grade") is None and rec.get("ai_system_grade_level"):
        rec["overall_grade"] = str(rec["ai_system_grade_level"]).strip().upper()

    _save_doc(doc)
    return {
        "ok": True,
        "submission_id": submission_id,
        "criteria_applied": applied,
        "progress": record_progress(rec),
    }
