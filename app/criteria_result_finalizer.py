"""
Final criteria pass — align achieved/score/feedback after all grading layers.

Fixes Godot export submissions where AI + artifacts support Pass but intermediate
layers (evidence gate, runtime smoke-only) left achieved=False with positive feedback.

Also provides DB sync — results.html reads GradingResult rows, not snapshot alone.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence

from app.btec_criteria_governance import (
    _FEEDBACK_CLAIMS_ACHIEVEMENT,
    _institutional_not_achieved_reason_ar,
    enforce_not_achieved_feedback_consistency,
)
from app.btec_grade_resolution import determine_grade_level

_GD_CODE_IN_TEXT = re.compile(
    r"(?:"
    r"\b[\w/\\]+\.gd\b|"
    r"\bgdscript\b|"
    r"\bgodot\b|"
    r"\bextends\s+(?:Node|CharacterBody2D|Area2D)\b|"
    r"\bfunc\s+\w+\s*\("
    r")",
    re.IGNORECASE,
)

def _text_has_test_plan_evidence(text: str) -> bool:
    from app.pro_evidence_signals import text_has_test_plan_evidence

    return text_has_test_plan_evidence(text)

_ARTIFACT_EXT_IN_TEXT = re.compile(
    r"[\w\s\-./\\]+\.(?:exe|apk|aab|pck)\b",
    re.IGNORECASE,
)

_EXEC_SHORT = frozenset({"P5", "P6", "P7"})
_PRO_PLAYTEST_GATED = frozenset({"P6", "M3", "D2", "D3"})


def _short_level(level: str) -> str:
    lv = (level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def _feedback_text(row: Dict[str, Any]) -> str:
    return str(row.get("feedback") or row.get("reasoning") or "").strip()


def _text_blob_for_row(row: Dict[str, Any], student_text: str) -> str:
    parts = [_feedback_text(row), student_text or ""]
    for pt in row.get("covered_points") or []:
        parts.append(str(pt))
    dm = row.get("decision_matrix") or []
    if isinstance(dm, list) and dm and isinstance(dm[0], dict):
        parts.append(str(dm[0].get("evidence") or ""))
        parts.append(str(dm[0].get("reasoning") or ""))
    return "\n".join(parts)


def _ai_supports_pass(row: Dict[str, Any]) -> bool:
    if row.get("ai_proposed_achieved"):
        return True
    fb = _feedback_text(row)
    if _FEEDBACK_CLAIMS_ACHIEVEMENT.search(fb):
        return True
    dm = row.get("decision_matrix") or []
    if isinstance(dm, list) and dm and isinstance(dm[0], dict):
        if dm[0].get("met") is True:
            return True
        reasoning = str(dm[0].get("reasoning") or "")
        if _FEEDBACK_CLAIMS_ACHIEVEMENT.search(reasoning):
            return True
    covered = row.get("covered_points") or []
    missing = row.get("missing_points") or []
    return bool(covered) and not missing


def _paths_from_inventory(inv: Dict[str, Any]) -> List[str]:
    paths: List[str] = []
    for key in ("executable_artifacts", "source_code", "documentation"):
        block = inv.get(key) or {}
        for f in block.get("files") or []:
            if isinstance(f, dict):
                p = f.get("path") or f.get("name") or ""
                if p:
                    paths.append(str(p))
            elif f:
                paths.append(str(f))
    return paths


def _resolve_assets(
    grading_result: Dict[str, Any],
    inventory: Optional[Dict[str, Any]],
) -> Dict[str, bool]:
    inv = inventory or grading_result.get("artifact_inventory") or {}
    gate = grading_result.get("evidence_completeness_gate") or {}
    assets = dict(gate.get("assets_detected") or {})

    has_exe = bool(
        inv.get("has_executable_artifacts")
        or assets.get("executable")
        or (inv.get("executable_artifacts") or {}).get("files")
    )
    has_src = bool(
        inv.get("has_source_code_artifacts")
        or assets.get("source_code")
        or (inv.get("source_code") or {}).get("files")
    )
    has_doc = bool(
        (inv.get("documentation") or {}).get("files")
        or assets.get("word_pdf")
    )

    path_candidates: List[str] = []
    path_candidates.extend(grading_result.get("submission_paths") or [])
    path_candidates.extend((gate.get("expanded_paths_sample") or []))
    path_candidates.extend(_paths_from_inventory(inv))
    for rel in grading_result.get("intake_relative_paths") or []:
        path_candidates.append(str(rel))

    try:
        from app.evidence_completeness_gate import _classify_paths, _godot_export_counts_as_source

        classified = _classify_paths(path_candidates)
        has_exe = has_exe or bool(classified.get("has_executable"))
        has_src = has_src or bool(classified.get("has_source_code"))
        has_doc = has_doc or bool(classified.get("has_word_pdf"))
        if not has_src:
            has_src = _godot_export_counts_as_source(path_candidates)
    except Exception:
        for raw in path_candidates:
            ext = Path(raw).suffix.lower()
            if ext in (".exe", ".apk", ".aab", ".pck"):
                has_exe = True
            if ext in (".gd", ".cs", ".py", ".gml"):
                has_src = True
            if ext in (".docx", ".doc", ".pdf"):
                has_doc = True

    if not has_src:
        for f in (inv.get("source_code") or {}).get("files") or []:
            if isinstance(f, dict) and f.get("source_kind") == "godot_pck_embedded":
                has_src = True
                break

    text_scan = str(grading_result.get("student_text") or "")
    for row in grading_result.get("criteria_results") or []:
        if isinstance(row, dict):
            text_scan += "\n" + _text_blob_for_row(row, "")

    if _ARTIFACT_EXT_IN_TEXT.search(text_scan):
        has_exe = True
    if _GD_CODE_IN_TEXT.search(text_scan):
        has_src = True
    if _text_has_test_plan_evidence(text_scan):
        has_doc = True

    obs = inv.get("runtime_observation_report") or {}
    for a in obs.get("artifact_analyses") or []:
        if a.get("type") in ("pck", "apk", "exe") and a.get("valid"):
            has_exe = True
        if a.get("type") == "pck" and a.get("valid"):
            has_src = True

    return {"has_exe": has_exe, "has_src": has_src, "has_doc": has_doc}


def _deliverable_pass_for_row(
    row: Dict[str, Any],
    *,
    student_text: str,
    assets: Dict[str, bool],
) -> bool:
    if not assets.get("has_exe"):
        return False
    if not _ai_supports_pass(row):
        return False
    short = _short_level(str(row.get("criteria_level") or ""))
    blob = _text_blob_for_row(row, student_text)
    if short == "P5":
        return bool(assets.get("has_src") or _GD_CODE_IN_TEXT.search(blob))
    if short == "P6":
        return (
            _text_has_test_plan_evidence(blob)
            and (assets.get("has_doc") or _text_has_test_plan_evidence(_feedback_text(row)))
        )
    return False


_GOVERNANCE_DENIAL_LEAD = re.compile(
    r"^[ \t]*⚠️\s*\[حوكمة BTEC\]\s*لم يتحقق المعيار مؤسسياً[^\n]*\n+",
    re.MULTILINE,
)
_AI_SECTION = re.compile(
    r"\[تحليل الذكاء الاصطناعي[^\]]*\]\s*\n?",
    re.IGNORECASE,
)


def _teacher_facing_feedback(row: Dict[str, Any]) -> str:
    """Strip internal governance denial wrapper; keep student-facing AI narrative."""
    from app.btec_criteria_governance import strip_btec_governance_feedback

    fb = strip_btec_governance_feedback(str(row.get("feedback") or ""))
    fb = _GOVERNANCE_DENIAL_LEAD.sub("", fb).strip()
    if _AI_SECTION.search(fb):
        fb = _AI_SECTION.sub("", fb, count=1).strip()
    if not fb or not _FEEDBACK_CLAIMS_ACHIEVEMENT.search(fb):
        dm = row.get("decision_matrix") or []
        if isinstance(dm, list) and dm and isinstance(dm[0], dict):
            fb = str(dm[0].get("reasoning") or dm[0].get("evidence") or fb).strip()
    return fb


def _promote_row(row: Dict[str, Any], *, reason_ar: str, authority: str) -> None:
    if not row.get("ai_proposed_achieved"):
        row["ai_proposed_achieved"] = True
    row["achieved"] = True
    row["verdict_status"] = "pass"
    row["score"] = max(int(row.get("score") or 0), 75)
    row["achievement_authority"] = authority
    row["governance_adjustment_ar"] = ""
    row["deliverable_pass_ar"] = reason_ar
    clean_fb = _teacher_facing_feedback(row)
    if clean_fb:
        row["feedback"] = clean_fb
    row["awardable"] = True
    row.pop("award_block_reason", None)
    row.pop("award_block_reason_ar", None)
    if isinstance(row.get("decision_matrix"), list) and row["decision_matrix"]:
        if isinstance(row["decision_matrix"][0], dict):
            row["decision_matrix"][0]["met"] = True
    det = row.get("deterministic_rubric")
    if isinstance(det, dict):
        det["deterministic_achieved"] = True
        det["verdict_status"] = "pass"
        det["reason"] = "deliverable_game_artifacts_and_report"


def _pearson_pro_blocks_promotion(
    grading_result: Dict[str, Any], short: str, row: Dict[str, Any]
) -> bool:
    # Runtime gate hold is absolute and mode-independent: once a runtime-dependent
    # criterion is blocked for lack of runtime evidence, NO path may re-promote it.
    if row.get("runtime_gate_block"):
        return True
    if not grading_result.get("pearson_btec_pro"):
        return False
    if row.get("pro_gameplay_governance_hold"):
        return True
    return short in _PRO_PLAYTEST_GATED


def reconcile_authoritative_achieved(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Single source of truth for achieved/score — fixes split state (score 75 + achieved false).
    """
    changes: List[str] = []
    assets = _resolve_assets(grading_result, artifact_inventory)
    text = str(grading_result.get("student_text") or "")
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short not in ("P5", "P6", "P7", "M3"):
            continue
        if _pearson_pro_blocks_promotion(grading_result, short, row):
            continue
        det = row.get("deterministic_rubric") or {}
        det_ok = bool(det.get("deterministic_achieved"))
        verdict = str(row.get("verdict_status") or det.get("verdict_status") or "").lower()
        score = int(row.get("score") or 0)
        should_pass = (
            det_ok
            or verdict == "pass"
            or (score >= 75 and _ai_supports_pass(row))
            or _deliverable_pass_for_row(row, student_text=text, assets=assets)
        )
        if not should_pass:
            continue
        if row.get("achieved"):
            clean = _teacher_facing_feedback(row)
            if clean and clean != row.get("feedback"):
                row["feedback"] = clean
                changes.append(f"{row.get('criteria_level')}:feedback_cleaned")
            continue
        label = "إنتاج/اختبار اللعبة" if short in ("P5", "P6") else "معيار التنفيذ"
        _promote_row(
            row,
            reason_ar=f"{label}: الأدلة والتحليل يثبتان تحقق المعيار (تسوية مؤسسية نهائية).",
            authority=str(det.get("authority") or "AUTHORITATIVE_RECONCILE"),
        )
        changes.append(f"{row.get('criteria_level')}:authoritative_reconcile")
    if changes:
        grading_result["grade_level"] = determine_grade_level(
            grading_result.get("criteria_results") or []
        )
        criteria = grading_result.get("criteria_results") or []
        total = sum(int(r.get("score") or 0) for r in criteria if isinstance(r, dict))
        n = len(criteria) or 1
        pct = int(total / n)
        grading_result["percentage"] = pct
        grading_result["total_score"] = pct
        grading_result["criteria_score_pct"] = pct
    return changes


def apply_deliverable_game_criteria_pass(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Pass P5/P6 when exe/apk/pck + report + AI agreement — without L5-only smoke."""
    changes: List[str] = []
    assets = _resolve_assets(grading_result, artifact_inventory)
    if not assets["has_exe"]:
        return changes
    text = str(grading_result.get("student_text") or "")
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short not in ("P5", "P6"):
            continue
        if _pearson_pro_blocks_promotion(grading_result, short, row):
            continue
        if row.get("achieved"):
            continue
        if not _deliverable_pass_for_row(row, student_text=text, assets=assets):
            continue
        label = "إنتاج اللعبة" if short == "P5" else "اختبار اللعبة"
        _promote_row(
            row,
            reason_ar=(
                f"{label}: ملفات تنفيذية (.exe/.apk/.pck) + تقرير/أدلة موثّقة "
                f"— تحقق Pass وفق مسار التسليم (deliverable artifacts)."
            ),
            authority="DELIVERABLE_ARTIFACT_PASS",
        )
        changes.append(f"{row.get('criteria_level')}:deliverable_pass")
    if changes:
        grading_result["grade_level"] = determine_grade_level(
            grading_result.get("criteria_results") or []
        )
    return changes


def patch_evidence_gate_from_inventory(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> None:
    """Reconcile evidence_completeness_gate with detected inventory (fixes false source_code gaps)."""
    gate = grading_result.get("evidence_completeness_gate")
    if not isinstance(gate, dict):
        return
    assets = _resolve_assets(grading_result, artifact_inventory)
    detected = {
        "word_pdf": assets["has_doc"],
        "source_code": assets["has_src"],
        "executable": assets["has_exe"],
    }
    gate["assets_detected"] = detected
    missing_any = False
    for row in gate.get("per_criterion") or []:
        if not isinstance(row, dict):
            continue
        fixed_missing = []
        for req in row.get("required_artifacts") or []:
            ok = True
            if req == "source_code":
                ok = assets["has_src"]
            elif req == "executable":
                ok = assets["has_exe"]
            elif req in (
                "gdd_document",
                "peer_review_document",
                "review_document",
                "testing_evidence",
            ):
                ok = assets["has_doc"] or (
                    req == "testing_evidence" and assets["has_exe"]
                )
            elif req in ("supporting_documentation", "evaluative_documentation"):
                ok = assets["has_doc"] or assets["has_src"]
            if not ok:
                fixed_missing.append(req)
        row["missing_artifacts"] = fixed_missing
        row["satisfied"] = not fixed_missing
        if fixed_missing:
            missing_any = True
    gate["has_gaps"] = missing_any


def finalize_grading_criteria_results(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Last pass before snapshot/UI — promote fair Pass paths and sync feedback."""
    grading_result.setdefault("submission_paths", [])
    patch_evidence_gate_from_inventory(grading_result, artifact_inventory=artifact_inventory)

    changes: List[str] = []
    changes.extend(
        reconcile_authoritative_achieved(
            grading_result, artifact_inventory=artifact_inventory
        )
    )
    changes.extend(
        apply_deliverable_game_criteria_pass(
            grading_result, artifact_inventory=artifact_inventory
        )
    )
    changes.extend(
        reconcile_authoritative_achieved(
            grading_result, artifact_inventory=artifact_inventory
        )
    )
    changes.extend(
        enforce_not_achieved_feedback_consistency(
            grading_result.get("criteria_results") or []
        )
    )
    from app.btec_criteria_governance import sanitize_all_criteria_feedback

    changes.extend(
        sanitize_all_criteria_feedback(grading_result.get("criteria_results") or [])
    )
    if grading_result.get("pearson_btec_pro"):
        try:
            from app.btec_criteria_governance import apply_btec_awardability
            from app.pro_btec_pearson import institutional_grade_from_awardable

            criteria = grading_result.get("criteria_results") or []
            apply_btec_awardability(criteria)
            inst = institutional_grade_from_awardable(criteria)
            grading_result["grade_level"] = inst
            award = grading_result.get("btec_institutional_award") or {}
            if isinstance(award, dict):
                award["institutional_grade"] = inst
                award["institutional_grade_from_awardable"] = inst
                grading_result["btec_institutional_award"] = award
        except Exception:
            pass
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        if row.get("achieved"):
            continue
        gov = str(row.get("governance_adjustment_ar") or "")
        if "لا توجد ملفات مشروع" in gov:
            assets = _resolve_assets(grading_result, artifact_inventory)
            if assets["has_exe"]:
                row["governance_adjustment_ar"] = ""

    if changes:
        criteria = grading_result.get("criteria_results") or []
        grading_result["grade_level"] = determine_grade_level(criteria)
        total = sum(int(r.get("score") or 0) for r in criteria if isinstance(r, dict))
        n = len(criteria) or 1
        pct = int(total / n)
        grading_result["percentage"] = pct
        grading_result["total_score"] = pct
        grading_result["criteria_score_pct"] = pct

    # TERMINAL SEAL — runtime evidence gate runs LAST so no promotion above can
    # leak a runtime-dependent Pass/Merit/Distinction without real runtime evidence.
    # Runs here because finalize_grading_criteria_results is invoked on grade, on
    # DB persist, and on every results/Word/PDF read path → single source of truth.
    try:
        from app.runtime_evidence_gate import apply_runtime_evidence_gate

        gate_report = apply_runtime_evidence_gate(
            grading_result, artifact_inventory=artifact_inventory
        )
        if gate_report.get("changes"):
            changes.extend(gate_report["changes"])
    except Exception:
        pass

    grading_result["criteria_finalizer"] = {
        "version": "criteria_finalizer_v3",
        "changes": changes,
    }
    return {"changes": changes, "change_count": len(changes)}


def _criteria_level_match(stored_level: str, target_level: str) -> bool:
    stored = (stored_level or "").strip().upper()
    target = (target_level or "").strip().upper()
    if not stored or not target:
        return False
    if stored == target:
        return True
    return stored.split(".")[-1] == target.split(".")[-1]


def sync_criteria_results_to_db(
    db: Any,
    submission_id: int,
    grading_result: Dict[str, Any],
) -> Dict[str, Any]:
    """Mirror finalized criteria_results into GradingResult + GradingSummary rows."""
    from app.models import GradingResult, GradingSummary

    db_results = (
        db.query(GradingResult).filter(GradingResult.submission_id == submission_id).all()
    )
    if not db_results:
        return {"synced": False, "reason": "no_db_rows"}

    changes: List[str] = []
    by_level: Dict[str, Dict[str, Any]] = {}
    for cr in grading_result.get("criteria_results") or []:
        if isinstance(cr, dict) and cr.get("criteria_level"):
            lvl = str(cr["criteria_level"])
            by_level[lvl] = cr
            by_level[_short_level(lvl)] = cr

    for db_row in db_results:
        crit = db_row.criteria
        if not crit:
            continue
        level = str(crit.criteria_level or "")
        snap = by_level.get(level) or by_level.get(_short_level(level))
        if not snap:
            continue
        new_ach = bool(snap.get("achieved"))
        new_score = int(snap.get("score") or 0)
        from app.btec_criteria_governance import teacher_facing_feedback

        new_fb = teacher_facing_feedback(snap.get("feedback") or "")
        if db_row.achieved != new_ach or int(db_row.score or 0) != new_score:
            db_row.achieved = new_ach
            db_row.score = new_score
            changes.append(level)
        if new_fb and teacher_facing_feedback(db_row.feedback or "") != new_fb:
            db_row.feedback = new_fb

    summary = (
        db.query(GradingSummary).filter(GradingSummary.submission_id == submission_id).first()
    )
    if summary:
        if grading_result.get("grade_level"):
            summary.grade_level = str(grading_result["grade_level"])
        if grading_result.get("percentage") is not None:
            summary.percentage = float(grading_result["percentage"])
        if grading_result.get("total_score") is not None:
            summary.total_score = int(grading_result["total_score"])

    if changes:
        db.commit()
    return {"synced": bool(changes), "levels": changes}
