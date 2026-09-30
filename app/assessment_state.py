"""Automated assessment state — "Cannot Run != Not Achieved".

The state is a *pure function* of the grading result (runtime session outcome,
criteria rows, gate errors); it is recomputed at the end of
``finalize_grading_criteria_results`` and stored at
``grading_result["assessment_state"]`` together with an evidence fingerprint.

States:  PAUSED | PROVISIONAL | FINAL  (SUBMITTED/ANALYZING/RUNTIME_REQUIRED are
pipeline phases owned by the worker and reported through ``resume_from``).

Per-criterion verification taxonomy (gated criteria P5/P6/M3/D3):

  VERIFIED_BY_RUNTIME      the game was run and the requirement was verified
  VERIFIED_BY_CODE         proven from code where that is an accepted path
  NOT_VERIFIED_BLOCKED     could not verify: platform/dependency/environment
  MISSING_EVIDENCE         the student did not submit the required evidence
  NOT_ACHIEVED_BY_RUNTIME  the game was run and the requirement was not met

``NOT_VERIFIED_BLOCKED`` and ``MISSING_EVIDENCE`` never become "Not Achieved":
no final grade is issued while any of them is open.  No human confirmation
exists anywhere in this flow; resuming is automatic when the blocker's
fingerprint changes (dependency installed / file uploaded).
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

VERIFIED_BY_RUNTIME = "VERIFIED_BY_RUNTIME"
VERIFIED_BY_CODE = "VERIFIED_BY_CODE"
NOT_VERIFIED_BLOCKED = "NOT_VERIFIED_BLOCKED"
MISSING_EVIDENCE = "MISSING_EVIDENCE"
NOT_ACHIEVED_BY_RUNTIME = "NOT_ACHIEVED_BY_RUNTIME"

STATE_PAUSED = "PAUSED"
STATE_PROVISIONAL = "PROVISIONAL"
STATE_FINAL = "FINAL"

GATED_SHORT = ("P5", "P6", "M3", "D3")
_RUN_ATTEMPTED = {"completed", "partial", "failed", "crashed", "timeout"}
_PAUSE_MARK_STATUSES = {"PAUSED", "PROVISIONAL_BLOCKED"}


def evidence_grace_days() -> int:
    """``EVIDENCE_GRACE_DAYS`` — 0 (default) means a PAUSED submission never expires."""
    try:
        return max(0, int(os.environ.get("EVIDENCE_GRACE_DAYS", "0") or 0))
    except ValueError:
        return 0


def _short(level: Any) -> str:
    lv = str(level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def _runtime_report(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    inv = grading_result.get("artifact_inventory") or {}
    report = inv.get("runtime_observation_report") or grading_result.get("runtime_observation_report")
    return report if isinstance(report, dict) else {}


def collect_blockers(grading_result: Dict[str, Any]) -> List[Dict[str, str]]:
    """Runtime-session blockers + gate error, as machine-readable dicts."""
    blockers: List[Dict[str, str]] = []
    seen = set()
    for raw in _runtime_report(grading_result).get("runtime_blockers") or []:
        if isinstance(raw, dict) and raw.get("code") and raw["code"] not in seen:
            seen.add(raw["code"])
            blockers.append({k: str(raw.get(k) or "") for k in ("code", "kind", "detail", "resolvable_by")})
    err = grading_result.get("runtime_gate_error")
    if isinstance(err, dict) and "runtime_gate_error" not in seen:
        blockers.append(
            {
                "code": "runtime_gate_error",
                "kind": "ENV_FAULT",
                "detail": str(err.get("error") or "runtime evidence gate failed")[:200],
                "resolvable_by": "retry",
            }
        )
    return blockers


def _run_was_attempted(grading_result: Dict[str, Any]) -> bool:
    report = _runtime_report(grading_result)
    status = str(report.get("status") or "").lower()
    return status in _RUN_ATTEMPTED and not report.get("runtime_blockers")


def _test_docs_missing(grading_result: Dict[str, Any]) -> bool:
    try:
        from app.gameplay_verifier import count_test_document_entries

        inv = dict(grading_result.get("artifact_inventory") or {})
        inv["intake_relative_paths"] = (
            grading_result.get("intake_relative_paths")
            or inv.get("intake_relative_paths")
            or grading_result.get("submission_paths")
            or []
        )
        return count_test_document_entries(inv) <= 0
    except Exception:
        return False


def classify_criteria(
    grading_result: Dict[str, Any], blockers: List[Dict[str, str]]
) -> Dict[str, str]:
    """Taxonomy label for each gated criterion present in the result."""
    rows = {
        _short(r.get("criteria_level")): r
        for r in (grading_result.get("criteria_results") or [])
        if isinstance(r, dict) and _short(r.get("criteria_level")) in GATED_SHORT
    }
    out: Dict[str, str] = {}
    blocked = any(b["kind"] in ("MISSING_DEPENDENCY", "ENV_FAULT") for b in blockers)
    missing_artifact = any(b["kind"] == "MISSING_ARTIFACT" for b in blockers)
    ran = _run_was_attempted(grading_result)
    docs_missing = _test_docs_missing(grading_result)
    for short, row in rows.items():
        achieved = bool(row.get("achieved")) and row.get("awardable") is not False
        if achieved and row.get("runtime_l4_verified"):
            out[short] = VERIFIED_BY_RUNTIME
        elif achieved and not row.get("runtime_gate_block"):
            out[short] = VERIFIED_BY_CODE
        elif blocked:
            out[short] = NOT_VERIFIED_BLOCKED
        elif missing_artifact or (short in ("P6", "M3") and docs_missing and not achieved):
            out[short] = MISSING_EVIDENCE
        elif short == "D3" and row.get("dependency_blocked_by") and any(
            v in (NOT_VERIFIED_BLOCKED, MISSING_EVIDENCE) for v in out.values()
        ):
            out[short] = NOT_VERIFIED_BLOCKED
        elif ran:
            out[short] = NOT_ACHIEVED_BY_RUNTIME
        else:
            out[short] = NOT_VERIFIED_BLOCKED
    return out


def _fingerprint(blockers: List[Dict[str, str]], decided: Dict[str, str], grading_result: Dict[str, Any]) -> str:
    payload = {
        "blockers": sorted(b["code"] for b in blockers),
        "decided": decided,
        "run": str(_runtime_report(grading_result).get("status") or ""),
        "files": len(grading_result.get("submission_paths") or []),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:16]


def _parse_ts(value: Any) -> Optional[datetime]:
    try:
        ts = datetime.fromisoformat(str(value))
        return ts if ts.tzinfo else ts.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def compute_assessment_state(
    grading_result: Dict[str, Any], *, now: Optional[datetime] = None
) -> Dict[str, Any]:
    """Pure: derive the state from evidence.  Only ``paused_since`` is carried over."""
    now = now or datetime.now(timezone.utc)
    prior = grading_result.get("assessment_state") if isinstance(grading_result.get("assessment_state"), dict) else {}
    blockers = collect_blockers(grading_result)
    decided = classify_criteria(grading_result, blockers)

    open_labels = {NOT_VERIFIED_BLOCKED, MISSING_EVIDENCE}
    has_open = any(v in open_labels for v in decided.values())
    dependency_or_env = any(b["kind"] in ("MISSING_DEPENDENCY", "ENV_FAULT") for b in blockers)

    if dependency_or_env and blockers and blockers[0]["code"] != "runtime_gate_error":
        state, resume_from = STATE_PAUSED, "runtime"
    elif any(b["code"] == "runtime_gate_error" for b in blockers):
        state, resume_from = STATE_PROVISIONAL, "finalizing"
    elif any(b["kind"] == "MISSING_ARTIFACT" for b in blockers) or MISSING_EVIDENCE in decided.values():
        state, resume_from = STATE_PAUSED, "extracting"
    elif has_open:
        state, resume_from = STATE_PROVISIONAL, "runtime"
    else:
        state, resume_from = STATE_FINAL, None

    paused_since = prior.get("paused_since")
    if state == STATE_PAUSED:
        paused_since = paused_since or now.isoformat()
        grace = evidence_grace_days()
        since = _parse_ts(paused_since)
        only_missing_evidence = bool(decided) and all(
            v in (MISSING_EVIDENCE, VERIFIED_BY_RUNTIME, VERIFIED_BY_CODE, NOT_ACHIEVED_BY_RUNTIME)
            for v in decided.values()
        ) and not dependency_or_env
        # Platform faults never expire against the student; only a missing upload can.
        if grace and since and only_missing_evidence and now - since >= timedelta(days=grace):
            state, resume_from = STATE_FINAL, None
    else:
        paused_since = None

    return {
        "version": "assessment_state_v1",
        "state": state,
        "blockers": blockers,
        "resume_from": resume_from,
        "decided": decided,
        "final_grade_allowed": state == STATE_FINAL,
        "evidence_fingerprint": _fingerprint(blockers, decided, grading_result),
        "paused_since": paused_since,
        "grace_days": evidence_grace_days(),
    }


def _blocked_reason_ar(state: Dict[str, Any], label: str) -> str:
    if label == MISSING_EVIDENCE:
        return "لم يقدّم الطالب الدليل المطلوب — لا يصدر حكم نهائي قبل رفعه."
    details = "; ".join(b["detail"] for b in state["blockers"]) or "تعذّر التشغيل"
    return f"لم تُشغَّل اللعبة ولم يُحكم على المعيار: {details}. سيُستأنف التصحيح تلقائيًا عند توفر المتطلب."


def apply_assessment_state(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    """Compute, store, and stamp the state.  Idempotent; never raises."""
    try:
        state = compute_assessment_state(grading_result)
    except Exception as exc:  # pragma: no cover - defensive
        return {"applied": False, "error": f"{type(exc).__name__}: {exc}"}
    grading_result["assessment_state"] = state

    criteria = [r for r in (grading_result.get("criteria_results") or []) if isinstance(r, dict)]
    for row in criteria:
        label = state["decided"].get(_short(row.get("criteria_level")))
        if label:
            row["verification_status"] = label
            generic = row.get("award_block_reason") in (None, "", "runtime_not_verified", "runtime_blocked", "missing_evidence")
            if label in (NOT_VERIFIED_BLOCKED, MISSING_EVIDENCE) and not row.get("achieved") and generic:
                row["award_block_reason"] = (
                    "runtime_blocked" if label == NOT_VERIFIED_BLOCKED else "missing_evidence"
                )
                row["award_block_reason_ar"] = _blocked_reason_ar(state, label)

    if state["state"] == STATE_FINAL:
        if grading_result.get("grade_decision_status") in _PAUSE_MARK_STATUSES:
            for key in ("grade_decision_status", "official_grade_provisional", "evidence_required"):
                grading_result.pop(key, None)
        grading_result.pop("final_grade_allowed", None)
        return {"applied": True, "state": STATE_FINAL}

    # PAUSED / PROVISIONAL: the grade is provisional and no final grade is issued.
    if grading_result.get("grade_decision_status") != "NOT_VERIFIED":
        grading_result["grade_decision_status"] = (
            "PAUSED" if state["state"] == STATE_PAUSED else "PROVISIONAL_BLOCKED"
        )
        grading_result["evidence_required"] = (
            "RUNTIME_DEPENDENCY_REQUIRED"
            if any(b["kind"] != "MISSING_ARTIFACT" for b in state["blockers"])
            else "STUDENT_EVIDENCE_REQUIRED"
        )
    grading_result["official_grade_provisional"] = True
    grading_result["final_grade_allowed"] = False
    grading_result.setdefault("grade_level_provisional", grading_result.get("grade_level"))
    for stale_key in ("institutional_resolution", "grade_display_metrics", "btec_institutional_award"):
        grading_result.pop(stale_key, None)
    return {"applied": True, "state": state["state"]}
