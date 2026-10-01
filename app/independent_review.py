"""Independent-review governance: deterministic decides, AI review only annotates.

* The DETERMINISTIC review is the basis of every decision.  It is derived from the
  same evidence the gates use (``assessment_state`` + criteria rows) and can produce
  the final decision on its own once runtime/evidence conditions are complete.
* The AI review is AUXILIARY: a diagnostic record.  It can never change a grade,
  an achievement, a score, ``assessment_state`` or the final/provisional status,
  and it cannot turn PAUSED / PROVISIONAL into final, nor replace a real
  ``NOT_ACHIEVED_BY_RUNTIME`` with a positive opinion.
* Any AI-vs-deterministic disagreement is recorded (``effect: "none"``); it never
  triggers a change, and no human step is created or required.

``run_governed_secondary_review`` wraps the existing secondary reviewer and
enforces this contract with a snapshot/restore guard, so even a reviewer policy
that tries to write a grade or status cannot leak it into the result.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from app.assessment_state import (
    MISSING_EVIDENCE,
    NOT_ACHIEVED_BY_RUNTIME,
    NOT_VERIFIED_BLOCKED,
    STATE_FINAL,
    VERIFIED_BY_CODE,
    VERIFIED_BY_RUNTIME,
    compute_assessment_state,
)

VERSION = "independent_review_v1"

DET_ACHIEVED = "ACHIEVED"
DET_NOT_ACHIEVED = "NOT_ACHIEVED"
DET_NOT_VERIFIED = "NOT_VERIFIED"

REL_AGREE = "AGREE"
REL_DISAGREE = "DISAGREE"
REL_NOT_COMPARABLE = "NOT_COMPARABLE"

# Top-level fields an auxiliary review must never change.
PROTECTED_RESULT_KEYS = (
    "grade_level",
    "grade_level_provisional",
    "percentage",
    "total_score",
    "criteria_score_pct",
    "grade_decision_status",
    "official_grade_provisional",
    "final_grade_allowed",
    "evidence_required",
    "human_review_required",
    "assessment_state",
    "provenance_history",
)
# Row fields an auxiliary review must never change.
PROTECTED_ROW_KEYS = (
    "achieved",
    "score",
    "awardable",
    "verdict_status",
    "verification_status",
    "runtime_gate_block",
    "achievement_authority",
    "award_block_reason",
    "award_block_reason_ar",
)
# Row flags an auxiliary review must not leave behind (they would re-open holds).
_ROW_FLAGS_REMOVED = ("secondary_review_hold", "secondary_review_auto_resolved")

_MISSING = object()


def _short(level: Any) -> str:
    text = str(level or "").strip().upper()
    return text.split(".")[-1] if "." in text else text


# ── deterministic review ────────────────────────────────────────────────────
def deterministic_review(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    """Pure: the deterministic decision per criterion + consistency conflicts."""
    state = compute_assessment_state(grading_result)
    decided = state.get("decided") or {}
    rows = [r for r in (grading_result.get("criteria_results") or []) if isinstance(r, dict)]
    decisions: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        short = _short(row.get("criteria_level"))
        label = decided.get(short)
        if label in (VERIFIED_BY_RUNTIME, VERIFIED_BY_CODE):
            decision = DET_ACHIEVED
        elif label == NOT_ACHIEVED_BY_RUNTIME:
            decision = DET_NOT_ACHIEVED
        elif label in (NOT_VERIFIED_BLOCKED, MISSING_EVIDENCE):
            decision = DET_NOT_VERIFIED
        else:  # criteria not gated by runtime: the gated row is the deterministic result
            decision = DET_ACHIEVED if row.get("achieved") else DET_NOT_ACHIEVED
        decisions[short] = {
            "criterion": row.get("criteria_level"),
            "decision": decision,
            "verification_status": label,
            "basis": "deterministic_gates" if label else "criteria_row_after_gates",
        }

    conflicts: List[Dict[str, str]] = []
    by_short = {_short(r.get("criteria_level")): r for r in rows}
    for short, row in by_short.items():
        label = decided.get(short)
        if row.get("achieved") and short in decided and label not in (VERIFIED_BY_RUNTIME, VERIFIED_BY_CODE):
            conflicts.append({"criterion": short, "code": "achieved_without_verification"})
    m3, d3 = by_short.get("M3"), by_short.get("D3")
    if d3 is not None and d3.get("achieved") and not (m3 and m3.get("achieved")):
        conflicts.append({"criterion": "D3", "code": "d3_without_m3"})
    inv = grading_result.get("artifact_inventory") or {}
    comparison = (inv.get("runtime_observation_report") or {}).get("version_runtime_comparison") or {}
    if m3 is not None and m3.get("achieved") and comparison.get("status") in (
        "PROVENANCE_MISMATCH", "IDENTICAL_BUILD",
    ):
        conflicts.append({"criterion": "M3", "code": "m3_with_unverifiable_version_comparison"})

    return {
        "version": VERSION,
        "authority": "DETERMINISTIC",
        "state": state["state"],
        "final_decision": state["state"] == STATE_FINAL,
        "final_grade_allowed": state["final_grade_allowed"],
        "blockers": state["blockers"],
        "decisions": decisions,
        "conflicts": conflicts,
        "consistent": not conflicts,
    }


# ── auxiliary comparison ────────────────────────────────────────────────────
def compare_auxiliary_review(
    deterministic: Dict[str, Any], audit: Dict[str, Any]
) -> Dict[str, Any]:
    """Pure: line the AI review up against the deterministic decisions.  effect is always none."""
    compared: List[Dict[str, Any]] = []
    for item in list(audit.get("agreements") or []) + list(audit.get("disagreements") or []):
        short = _short(item.get("criterion"))
        det = (deterministic.get("decisions") or {}).get(short)
        if det is None:
            continue
        ai = bool(item.get("reviewer_achieved"))
        verdict = det["decision"]
        if verdict == DET_NOT_VERIFIED:
            relation = REL_NOT_COMPARABLE  # a blocked verdict is never filled in by an opinion
        else:
            relation = REL_AGREE if ai == (verdict == DET_ACHIEVED) else REL_DISAGREE
        compared.append({
            "criterion": item.get("criterion"),
            "deterministic": verdict,
            "verification_status": det.get("verification_status"),
            "ai_achieved": ai,
            "relation": relation,
            "ai_positive_ignored": ai and verdict != DET_ACHIEVED,
            "confidence": item.get("confidence"),
            "reasoning": item.get("reasoning"),
            "effect": "none",
        })
    return {
        "compared": compared,
        "agreements": [c for c in compared if c["relation"] == REL_AGREE],
        "disagreements": [c for c in compared if c["relation"] == REL_DISAGREE],
        "not_comparable": [c for c in compared if c["relation"] == REL_NOT_COMPARABLE],
    }


# ── the guard ───────────────────────────────────────────────────────────────
def _grab(data: Dict[str, Any], key: str) -> Any:
    # The sentinel must stay the same object (a deepcopy would create a new one).
    return copy.deepcopy(data[key]) if key in data else _MISSING


def _snapshot(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    top = {k: _grab(grading_result, k) for k in PROTECTED_RESULT_KEYS}
    rows = []
    for row in grading_result.get("criteria_results") or []:
        rows.append(
            {k: _grab(row, k) for k in PROTECTED_ROW_KEYS}
            if isinstance(row, dict) else None
        )
    return {"top": top, "rows": rows}


def _restore(grading_result: Dict[str, Any], snap: Dict[str, Any]) -> Dict[str, Any]:
    """Undo any protected write; return what the reviewer tried to change (for the record)."""
    attempted: Dict[str, Any] = {}
    for key, before in snap["top"].items():
        now = grading_result.get(key, _MISSING)
        if now == before:
            continue
        attempted[key] = {"tried": None if now is _MISSING else now}
        if before is _MISSING:
            grading_result.pop(key, None)
        else:
            grading_result[key] = before
    for idx, row in enumerate(grading_result.get("criteria_results") or []):
        if not isinstance(row, dict) or snap["rows"][idx] is None:
            continue
        for key, before in snap["rows"][idx].items():
            now = row.get(key, _MISSING)
            if now == before:
                continue
            attempted[f"row[{idx}].{key}"] = {"tried": None if now is _MISSING else now}
            if before is _MISSING:
                row.pop(key, None)
            else:
                row[key] = before
        for flag in _ROW_FLAGS_REMOVED:
            if flag in row:
                attempted[f"row[{idx}].{flag}"] = {"tried": row.pop(flag)}
    return attempted


def run_governed_secondary_review(
    grading_result: Dict[str, Any],
    **review_kwargs: Any,
) -> Dict[str, Any]:
    """Run the AI reviewer as auxiliary evidence only; the deterministic result stands."""
    from app.secondary_ai_review import run_secondary_review

    deterministic = deterministic_review(grading_result)
    snap = _snapshot(grading_result)
    try:
        audit = run_secondary_review(grading_result, **review_kwargs)
    except Exception as exc:  # a broken reviewer must never affect the result
        audit = {"status": "REVIEW_UNAVAILABLE", "error": str(exc)[:300], "agreements": [], "disagreements": []}
    attempted = _restore(grading_result, snap)

    comparison = compare_auxiliary_review(deterministic, audit)
    legacy_status = audit.get("status")
    audit["authority"] = "AUXILIARY"
    audit["effect_on_grade"] = "none"
    audit["hold_required"] = False  # no hold and no human review is ever created
    audit["legacy_status"] = legacy_status
    if comparison["disagreements"]:
        audit["status"] = "DISAGREEMENT_RECORDED"
    grading_result["secondary_ai_review"] = audit
    grading_result["independent_review"] = {
        "version": VERSION,
        "decision_authority": "DETERMINISTIC",
        "deterministic": deterministic,
        "auxiliary_ai_review": {
            "authority": "AUXILIARY",
            "status": audit.get("status"),
            "effect_on_grade": "none",
            **comparison,
            "blocked_writes": attempted,
        },
    }
    return audit
