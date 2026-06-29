"""
Runtime Evidence Gate — Pearson-grade single authority for runtime-dependent criteria.

Golden rule (PRO governance):
    A runtime-dependent criterion (C.P5 / C.P6 / C.M3 / C.D3) may NOT be awarded
    unless the game was *actually* shown to run / be played. Documents, slides,
    images, AI description, static analysis (incl. Scratch static graph), and the
    mere *presence* of a project/.sb3/.exe are NOT sufficient on their own.

Accepted runtime evidence (any ONE satisfies the gate):
    1. Runtime PASS         — real launch + gameplay validation (engine sandbox)
    2. Gameplay video       — documented gameplay footage
    3. Human review (L5)    — teacher-verified / visually-corroborated playtest
    4. Human review recorded

If a submission is a game project but NONE of the above is present, every gated
criterion is forced to achieved=False / awardable=False and marked with a
non-bypassable ``runtime_gate_block`` flag so no later promotion path can re-award
it. The final BTEC band is then recomputed (a missing mandatory Pass criterion ⇒ U).

This module is the terminal "seal": it is invoked LAST in
``finalize_grading_criteria_results`` (which runs on grade, on DB persist, and on
every results/Word/PDF read path), so the same blocked decision is reflected in the
UI, the Word report, the PDF report, the API and the dashboard.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.btec_criteria_governance import _demote_row, _short_level
from app.btec_grade_resolution import determine_grade_level
from app.game_engine_signatures import (
    detect_engine_from_text,
    has_runnable_game_project,
)

GATE_VERSION = "runtime_evidence_gate_v1"

# Runtime-dependent criteria (per Pearson policy): prototype, testing, refinement
# merit, and the corresponding distinction band. Matches user spec C.P5/C.P6/C.M3/C.D3.
RUNTIME_GATED_SHORT = frozenset({"P5", "P6", "M3", "D3"})

_RUNTIME_GATE_AUTHORITY = "RUNTIME_GATE_BLOCKED"

_GATE_REASON_AR = (
    "بوابة التحقق من التشغيل (Runtime Gate): لم يُثبَت تشغيل/لعب اللعبة فعلياً. "
    "لا يُمنح هذا المعيار بالاعتماد على التقرير أو العرض التقديمي أو الصور أو "
    "التحليل الساكن أو مجرد وجود ملفات المشروع (.sb3/.exe). الأدلة المقبولة: "
    "تشغيل ناجح موثّق (Runtime PASS)، أو فيديو لعب (Gameplay Video)، أو مراجعة "
    "بشرية (L5 Playtest)."
)


def _collect_paths(
    grading_result: Optional[Dict[str, Any]],
    inventory: Optional[Dict[str, Any]],
) -> List[str]:
    pool: List[str] = []
    for src_obj in (grading_result or {}, inventory or {}):
        for key in ("submission_paths", "intake_relative_paths"):
            val = src_obj.get(key)
            if isinstance(val, list):
                pool.extend(str(p) for p in val if p)
    return pool


def is_game_submission(
    inventory: Optional[Dict[str, Any]],
    *,
    submission_paths: Optional[List[str]] = None,
) -> bool:
    """True when the submission is a runnable game project (any supported engine).

    Non-game assignments (networking, spreadsheets, essays, …) are never gated."""
    inv = inventory or {}
    rt = inv.get("runtime_artifacts") or {}
    if (
        rt.get("scratch_detected")
        or rt.get("gamemaker_detected")
        or rt.get("gamemaker_build_detected")
        or rt.get("godot_export_detected")
        or rt.get("unity_build_detected")
        or rt.get("html5_build_detected")
    ):
        return True
    if inv.get("has_executable_artifacts"):
        # executable_artifacts that are game builds (Scratch/exe/pck/apk/win)
        return True
    paths = list(submission_paths or []) + _collect_paths(None, inv)
    joined = "\n".join(paths).lower().replace("\\", "/")
    if joined and (has_runnable_game_project(joined) or detect_engine_from_text(joined)):
        return True
    return False


def evaluate_runtime_evidence(
    inventory: Optional[Dict[str, Any]],
    *,
    submission_paths: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Return the canonical runtime-evidence verdict for a submission.

    Reuses ``assess_playtest_evidence`` (the established accepted-evidence union:
    L5 human playtest, gameplay video, runtime+gameplay validation, human review).
    """
    inv = inventory or {}
    try:
        from app.pro_engine_gameplay_governance import assess_playtest_evidence

        assessment = assess_playtest_evidence(inv, submission_paths=submission_paths)
    except Exception as err:  # pragma: no cover - defensive
        return {
            "version": GATE_VERSION,
            "status": "UNKNOWN",
            "satisfied": False,
            "error": str(err),
            "accepted_evidence": [],
            "paths": {},
        }

    paths = assessment.get("playtest_paths") or {}
    satisfied = bool(assessment.get("any_path_satisfied"))
    accepted: List[str] = [k for k, v in paths.items() if v]
    return {
        "version": GATE_VERSION,
        "status": "PASS" if satisfied else "BLOCKED",
        "satisfied": satisfied,
        "engine_id": assessment.get("engine_id"),
        "accepted_evidence": accepted,
        "paths": paths,
        "structure_only_runtime": assessment.get("structure_only_runtime"),
        "summary_ar": assessment.get("summary_ar"),
    }


def _recompute_grade(grading_result: Dict[str, Any]) -> None:
    criteria = grading_result.get("criteria_results") or []
    grading_result["grade_level"] = determine_grade_level(criteria)
    total = sum(int(r.get("score") or 0) for r in criteria if isinstance(r, dict))
    pct = int(total / (len(criteria) or 1))
    grading_result["percentage"] = pct
    grading_result["total_score"] = pct
    grading_result["criteria_score_pct"] = pct


def apply_runtime_evidence_gate(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Terminal seal: block runtime-dependent criteria lacking real runtime evidence.

    Idempotent — safe to call multiple times across the pipeline / read paths.
    Returns a report dict (also stored at ``grading_result['runtime_evidence_gate']``).
    """
    criteria = grading_result.get("criteria_results")
    if not isinstance(criteria, list) or not criteria:
        return {"applied": False, "reason": "no_criteria"}

    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    submission_paths = _collect_paths(grading_result, inv)

    if not is_game_submission(inv, submission_paths=submission_paths):
        report = {
            "applied": False,
            "version": GATE_VERSION,
            "reason": "not_a_game_submission",
        }
        grading_result["runtime_evidence_gate"] = report
        return report

    verdict = evaluate_runtime_evidence(inv, submission_paths=submission_paths)

    changes: List[str] = []
    if not verdict["satisfied"]:
        for row in criteria:
            if not isinstance(row, dict):
                continue
            short = _short_level(str(row.get("criteria_level") or ""))
            if short not in RUNTIME_GATED_SHORT:
                continue
            # Record a change only when this row was actually awarding something.
            was_awarding = bool(row.get("achieved") or row.get("awardable"))
            # Always stamp the hold flag so promotion paths can never re-award,
            # even if a prior layer left the row achieved.
            row["runtime_gate_block"] = True
            _demote_row(row, _GATE_REASON_AR)  # no-op if already not achieved
            row["awardable"] = False
            row["achievement_authority"] = _RUNTIME_GATE_AUTHORITY
            row["award_block_reason"] = "runtime_not_verified"
            row["award_block_reason_ar"] = _GATE_REASON_AR
            if was_awarding:
                changes.append(f"{row.get('criteria_level')}:runtime_gate_block")
    else:
        # Runtime satisfied — clear any stale gate hold so legitimate awards stand.
        for row in criteria:
            if isinstance(row, dict) and row.get("runtime_gate_block"):
                row.pop("runtime_gate_block", None)

    if changes:
        _recompute_grade(grading_result)
        # Single source of truth: invalidate cached grade-display objects so every
        # downstream reader (UI, Word, PDF, API) re-derives from the gated grade_level
        # instead of a stale higher band (prevents "UI=U but report=M").
        for stale_key in (
            "institutional_resolution",
            "grade_display_metrics",
            "btec_institutional_award",
            "expected_runtime_grade",
        ):
            grading_result.pop(stale_key, None)

    report = {
        "applied": bool(changes),
        "version": GATE_VERSION,
        "runtime_status": verdict["status"],
        "satisfied": verdict["satisfied"],
        "accepted_evidence": verdict.get("accepted_evidence"),
        "engine_id": verdict.get("engine_id"),
        "gated_criteria": sorted(RUNTIME_GATED_SHORT),
        "changes": changes,
        "summary_ar": verdict.get("summary_ar"),
    }
    grading_result["runtime_evidence_gate"] = report
    return report
