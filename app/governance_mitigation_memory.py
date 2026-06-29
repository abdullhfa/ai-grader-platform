"""
Governance Mitigation Memory v1 — did the institutional response work over time?

Links: failure mode → mitigation applied → outcome observed → cohort learning.
Does not alter grades.
"""
from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

MEMORY_ID = "GOVERNANCE_MITIGATION_MEMORY_v1"
_LOG_DIR = Path(__file__).resolve().parent / "calibration" / "human_cohort_workshop"
_LOG_PATH = _LOG_DIR / "mitigations.jsonl"


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _read_log(limit: int = 5000) -> List[Dict[str, Any]]:
    if not _LOG_PATH.is_file():
        return []
    rows: List[Dict[str, Any]] = []
    try:
        with open(_LOG_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
    except OSError:
        return []
    return rows[-limit:]


def _append_log(record: Dict[str, Any]) -> Optional[str]:
    try:
        _LOG_DIR.mkdir(parents=True, exist_ok=True)
        with open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return str(_LOG_PATH)
    except OSError:
        return None


def record_mitigation_from_drift(
    *,
    submission_id: Optional[int] = None,
    student_name: str = "",
    batch_id: Optional[int] = None,
    governance_drift: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Persist mitigation records when governance responses fire on a submission.
    Called after grading — one record per response item.
    """
    drift = governance_drift or {}
    responses = (drift.get("governance_responses") or {}).get("responses") or []
    if not responses:
        return []

    created: List[Dict[str, Any]] = []
    for resp in responses:
        gfm = resp.get("failure_mode_id")
        if not gfm:
            continue
        rec = {
            "memory_id": MEMORY_ID,
            "mitigation_id": f"mit_{uuid.uuid4().hex[:12]}",
            "submission_id": submission_id,
            "student_name": student_name,
            "batch_id": batch_id,
            "failure_mode_id": gfm,
            "failure_mode_ar": resp.get("failure_mode_ar"),
            "severity_level": resp.get("severity_level"),
            "actions": resp.get("actions") or [],
            "actions_ar": resp.get("actions_ar") or [],
            "export_gate": (drift.get("governance_responses") or {}).get("export_policy", {}).get("gate"),
            "triggered_at": _utc_now(),
            "outcome": "pending",
            "outcome_ar": "بانتظار تقييم فعالية mitigation",
            "outcome_notes_ar": "",
            "outcome_recorded_at": None,
            "recurrence_detected": False,
        }
        path = _append_log(rec)
        if path:
            rec["log_path"] = path
        created.append(rec)
    return created


def record_mitigation_outcome(
    *,
    mitigation_id: str,
    outcome: str,
    notes_ar: str = "",
    recurrence_detected: bool = False,
    reviewer_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Record whether a mitigation worked (manual workshop or auto recurrence check).

    outcome: effective | partial | recurred | ineffective | unknown
    """
    valid = {"effective", "partial", "recurred", "ineffective", "unknown", "pending"}
    if outcome not in valid:
        outcome = "unknown"

    rows = _read_log()
    updated: Optional[Dict[str, Any]] = None
    rebuilt: List[Dict[str, Any]] = []
    for row in rows:
        if row.get("mitigation_id") == mitigation_id:
            row = {
                **row,
                "outcome": outcome,
                "outcome_ar": _outcome_label_ar(outcome),
                "outcome_notes_ar": notes_ar,
                "outcome_recorded_at": _utc_now(),
                "recurrence_detected": recurrence_detected,
                "reviewer_id": reviewer_id,
            }
            updated = row
        rebuilt.append(row)

    if updated:
        try:
            with open(_LOG_PATH, "w", encoding="utf-8") as f:
                for row in rebuilt:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
        except OSError:
            pass
    return updated or {"error": "mitigation_id_not_found", "mitigation_id": mitigation_id}


def _outcome_label_ar(outcome: str) -> str:
    return {
        "effective": "فعّال — لم يتكرر failure",
        "partial": "جزئي — تحسّن لكن ambiguity باقية",
        "recurred": "تكرر — mitigation لم يكفِ",
        "ineffective": "غير فعّال",
        "unknown": "غير معروف",
        "pending": "بانتظار التقييم",
    }.get(outcome, outcome)


def check_recurrence_for_submission(
    *,
    submission_id: int,
    current_drift: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Auto-check: compare current GFM set with pending mitigations for same submission.
    Marks recurred when same failure_mode_id appears again after mitigation.
    """
    current_gfms = {
        r.get("failure_mode_id")
        for r in (current_drift.get("governance_responses") or {}).get("responses") or []
        if r.get("failure_mode_id")
    }
    updates: List[Dict[str, Any]] = []
    for row in _read_log():
        if row.get("submission_id") != submission_id:
            continue
        if row.get("outcome") not in ("pending", None):
            continue
        gfm = row.get("failure_mode_id")
        if gfm and gfm in current_gfms:
            upd = record_mitigation_outcome(
                mitigation_id=str(row.get("mitigation_id")),
                outcome="recurred",
                notes_ar="تكرار failure mode تلقائياً عند re-grade",
                recurrence_detected=True,
            )
            if upd and "error" not in upd:
                updates.append(upd)
    return updates


def analyze_mitigation_effectiveness(
    *,
    cohort_id: Optional[str] = None,
    batch_id: Optional[int] = None,
    failure_mode_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate mitigation learning for pilot / cohort synthesis."""
    rows = _read_log()
    if batch_id is not None:
        rows = [r for r in rows if r.get("batch_id") == batch_id]
    if failure_mode_id:
        rows = [r for r in rows if r.get("failure_mode_id") == failure_mode_id]

    by_mode: Dict[str, Dict[str, int]] = {}
    for row in rows:
        gfm = str(row.get("failure_mode_id") or "UNKNOWN")
        bucket = by_mode.setdefault(gfm, {
            "total": 0,
            "effective": 0,
            "partial": 0,
            "recurred": 0,
            "ineffective": 0,
            "pending": 0,
            "unknown": 0,
        })
        bucket["total"] += 1
        oc = str(row.get("outcome") or "pending")
        if oc in bucket:
            bucket[oc] += 1
        else:
            bucket["unknown"] += 1

    effectiveness: List[Dict[str, Any]] = []
    for gfm, counts in sorted(by_mode.items(), key=lambda x: -x[1]["total"]):
        resolved = counts["effective"] + counts["partial"]
        decided = counts["total"] - counts["pending"]
        rate = round(resolved / decided, 3) if decided > 0 else None
        effectiveness.append({
            "failure_mode_id": gfm,
            "counts": counts,
            "effectiveness_rate": rate,
            "recurrence_rate": round(counts["recurred"] / decided, 3) if decided > 0 else None,
            "learning_ar": _learning_note_ar(gfm, counts, rate),
        })

    total = len(rows)
    pending = sum(1 for r in rows if r.get("outcome") == "pending")
    effective = sum(1 for r in rows if r.get("outcome") == "effective")

    return {
        "version": 1,
        "memory_id": MEMORY_ID,
        "cohort_id": cohort_id,
        "batch_id": batch_id,
        "record_count": total,
        "pending_count": pending,
        "effective_count": effective,
        "by_failure_mode": effectiveness,
        "summary_ar": (
            f"{total} mitigation(s) مسجّلة — "
            f"{effective} effective — {pending} pending — "
            "institutional mitigation learning (not grade adjustment)."
        ),
    }


def _learning_note_ar(gfm: str, counts: Dict[str, int], rate: Optional[float]) -> str:
    if counts["pending"] == counts["total"]:
        return f"{gfm}: mitigations مُطبّقة — بانتظار outcome من workshop."
    if counts["recurred"] > 0:
        return f"{gfm}: تكرار {counts['recurred']} — راجع response protocol."
    if rate is not None and rate >= 0.7:
        return f"{gfm}: mitigation فعّال نسبياً ({rate:.0%})."
    if rate is not None:
        return f"{gfm}: mitigation جزئي — يحتاج calibration."
    return f"{gfm}: بيانات outcome غير كافية."


def attach_mitigation_memory_to_cohort(cohort_report: Dict[str, Any]) -> Dict[str, Any]:
    """Enrich cohort governance metrics with mitigation learning."""
    batch_id = None
    cid = str(cohort_report.get("cohort_id") or "")
    if cid.startswith("batch_"):
        try:
            batch_id = int(cid.split("_", 1)[1])
        except (ValueError, IndexError):
            batch_id = None
    memory = analyze_mitigation_effectiveness(cohort_id=cid, batch_id=batch_id)
    return {**cohort_report, "mitigation_memory": memory}
