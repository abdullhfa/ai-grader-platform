"""
Advisory «expected grade if runtime verified» — UI/PDF only; does not mutate official grade.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional

from app.btec_grade_resolution import determine_grade_level

OFFICIAL_GRADE_LABEL_AR = "التقدير المعتمد"
EXPECTED_GRADE_LABEL_AR = "التقدير المتوقع (عند إكمال التشغيل والتأكد من اللعبة)"
EXPECTED_RUNTIME_DISCLAIMER_AR = (
    "بناء على الوثائق والصور والفيديو؛ التشغيل الفعلي لم يدقق. ( تحديث الخطة الى برو )"
)

_P5_INCONCLUSIVE_BASES = frozenset(
    {
        "inconclusive_no_runtime",
        "runtime_not_executed_basic_mode",
    }
)
_P6_INCONCLUSIVE_BASES = frozenset(
    {
        "inconclusive_no_structured_test_plan",
        "inconclusive_formal_testing_docs_required",
        "test_doc_basic_no_runtime",
    }
)
_P7_INCONCLUSIVE_BASES = _P5_INCONCLUSIVE_BASES


def _short_level(criteria_level: str) -> str:
    lv = (criteria_level or "").strip().upper()
    if "." in lv:
        lv = lv.split(".")[-1]
    return lv


def _authority_by_criterion(grading_result: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    out: Dict[str, Dict[str, Any]] = {}
    inv = grading_result.get("artifact_inventory") or {}
    rows = grading_result.get("criterion_authority") or inv.get("criterion_authority") or []
    for row in rows:
        if not isinstance(row, dict):
            continue
        key = _short_level(str(row.get("criterion") or ""))
        if key:
            out[key] = row
    return out


def _has_static_gameplay_evidence(grading_result: Dict[str, Any]) -> bool:
    inv = grading_result.get("artifact_inventory") or {}
    sc = inv.get("source_code") or inv.get("source_code_artifacts") or {}
    if sc.get("status") == "analyzed" or sc.get("files"):
        return True
    if inv.get("has_source_code_artifacts"):
        return True
    ves = grading_result.get("visual_evidence_summary") or inv.get("visual_evidence_summary") or {}
    if int(ves.get("images_used_in_decision") or ves.get("images_analyzed") or 0) > 0:
        return True
    if int(ves.get("video_keyframes_analyzed") or 0) > 0:
        return True
    vk = grading_result.get("basic_video_keyframes_meta") or inv.get("basic_video_keyframes_meta") or {}
    if int(vk.get("frames_extracted") or 0) > 0:
        return True
    return False


def _runtime_verified(grading_result: Dict[str, Any]) -> bool:
    inv = grading_result.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    ves = grading_result.get("visual_evidence_summary") or inv.get("visual_evidence_summary") or {}
    return bool(
        obs.get("runtime_verified")
        or ves.get("runtime_verified")
        or inv.get("runtime_verified")
    )


def _is_basic_mode(grading_result: Dict[str, Any]) -> bool:
    from app.grading_mode_policy import is_fast_grading_mode
    from app.rule_bundle import resolve_execution_mode

    mode = (
        grading_result.get("execution_mode")
        or resolve_execution_mode(grading_result.get("grading_mode"))
        or ""
    )
    if str(mode).upper() == "BASIC" or is_fast_grading_mode(grading_result.get("grading_mode")):
        return True
    prov = grading_result.get("decision_provenance") or {}
    return str(prov.get("execution_mode") or "").upper() == "BASIC"


def _should_flip_criterion(
    *,
    short: str,
    achieved: bool,
    verdict_status: str,
    decision_basis: str,
    grading_result: Dict[str, Any],
    requires_pro: bool = False,
    pro_gate_converted_from_fail: bool = False,
    ai_proposed_achieved: bool = False,
) -> bool:
    if achieved:
        return False
    if short not in ("P5", "P6", "P7"):
        return False
    if not _has_static_gameplay_evidence(grading_result):
        return False
    if not _is_basic_mode(grading_result):
        return False

    vs = (verdict_status or "").strip().lower()
    basis = (decision_basis or "").strip().lower()
    auth = _authority_by_criterion(grading_result).get(short) or {}
    if not basis:
        basis = str(auth.get("decision_basis") or "").strip().lower()
    result = str(auth.get("result") or "").strip().upper()

    if result == "FAIL" and vs == "fail" and basis in ("none", "") and not (
        "inconclusive" in basis
    ):
        return False

    if short == "P5":
        if vs == "inconclusive" or result == "INCONCLUSIVE" or "inconclusive" in basis:
            return basis in _P5_INCONCLUSIVE_BASES or "runtime" in basis or requires_pro
        if pro_gate_converted_from_fail and requires_pro:
            return basis in _P5_INCONCLUSIVE_BASES or "runtime" in basis
        return basis in _P5_INCONCLUSIVE_BASES or "runtime" in basis

    if short == "P6":
        if result == "FAIL" and vs == "fail" and basis in ("none", "") and not pro_gate_converted_from_fail:
            return False
        if not auth.get("testing_authority_available") and basis not in _P6_INCONCLUSIVE_BASES:
            return False
        if vs == "inconclusive" or result == "INCONCLUSIVE" or "inconclusive" in basis:
            return basis in _P6_INCONCLUSIVE_BASES or (
                bool(auth.get("testing_authority_available")) and "test" in basis
            )
        return basis in _P6_INCONCLUSIVE_BASES or basis == "test_doc_basic_no_runtime"

    if short == "P7":
        if result == "FAIL" and vs == "fail" and basis in ("none", ""):
            return False
        if ai_proposed_achieved:
            return True
        if vs == "inconclusive" or result == "INCONCLUSIVE" or "inconclusive" in basis:
            return basis in _P7_INCONCLUSIVE_BASES or "runtime" in basis or requires_pro
        if pro_gate_converted_from_fail and requires_pro:
            return basis in _P7_INCONCLUSIVE_BASES or "runtime" in basis
        return basis in _P7_INCONCLUSIVE_BASES or "runtime" in basis

    return False


def _cap_expected_grade(
    expected_short: str,
    counterfactual: List[Dict[str, Any]],
    original: List[Dict[str, Any]],
) -> str:
    """Expected cannot jump to D unless M/D were already achieved in official grading."""
    if expected_short != "D":
        return expected_short

    orig_by = {str(r.get("criteria_level")): r for r in original if isinstance(r, dict)}
    m_d_ok = all(
        bool(orig_by.get(lv, {}).get("achieved"))
        for lv in orig_by
        if _short_level(lv).startswith("M") or _short_level(lv).startswith("D")
    )
    if m_d_ok:
        return expected_short
    capped = determine_grade_level(counterfactual)
    if capped == "D":
        return "M" if all(
            r.get("achieved")
            for r in counterfactual
            if _short_level(str(r.get("criteria_level") or "")).startswith("M")
        ) else "P" if all(
            r.get("achieved")
            for r in counterfactual
            if _short_level(str(r.get("criteria_level") or "")).startswith("P")
        ) else "U"
    return capped


def build_counterfactual_criteria(criteria_results: List[Dict[str, Any]], grading_result: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Copy criteria with P5/P6/P7 flipped to achieved when static evidence supports expected runtime."""
    auth_map = _authority_by_criterion(grading_result)
    out: List[Dict[str, Any]] = []
    for row in criteria_results or []:
        if not isinstance(row, dict):
            continue
        cr = copy.deepcopy(row)
        short = _short_level(str(cr.get("criteria_level") or ""))
        auth = auth_map.get(short) or {}
        basis = str(auth.get("decision_basis") or cr.get("decision_basis") or "")
        if _should_flip_criterion(
            short=short,
            achieved=bool(cr.get("achieved")),
            verdict_status=str(cr.get("verdict_status") or ""),
            decision_basis=basis,
            grading_result=grading_result,
            requires_pro=bool(cr.get("requires_pro")),
            pro_gate_converted_from_fail=bool(cr.get("pro_gate_converted_from_fail")),
            ai_proposed_achieved=bool(cr.get("ai_proposed_achieved")),
        ):
            cr["achieved"] = True
            cr["verdict_status"] = "pass"
            cr["expected_runtime_flip"] = True
        out.append(cr)
    return out


def build_expected_runtime_grade_display(grading_result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Advisory dual-grade block for BASIC submissions without runtime verification.
    Returns None when not applicable. Shows when P5/P6/P7 would flip on runtime verify,
    even if the institutional band stays the same (e.g. other Pass criteria still missing).
    """
    work: Dict[str, Any] = dict(grading_result)
    work["criteria_results"] = [
        dict(r) if isinstance(r, dict) else r for r in (grading_result.get("criteria_results") or [])
    ]
    try:
        from app.visual_evidence_registry import apply_game_criteria_pro_gate

        apply_game_criteria_pro_gate(work, grading_mode=work.get("grading_mode"))
    except Exception:
        work = dict(grading_result)
        work["criteria_results"] = [
            dict(r) if isinstance(r, dict) else r for r in (grading_result.get("criteria_results") or [])
        ]

    if not _is_basic_mode(work):
        return None
    if _runtime_verified(work):
        return None
    if not _has_static_gameplay_evidence(work):
        return None

    criteria = work.get("criteria_results") or []
    if not criteria:
        return None

    official_short = determine_grade_level(criteria)

    cf_criteria = build_counterfactual_criteria(criteria, work)
    expected_short = determine_grade_level(cf_criteria)
    expected_short = _cap_expected_grade(
        expected_short,
        cf_criteria,
        list(grading_result.get("criteria_results") or []),
    )
    flipped = [
        str(r.get("criteria_level"))
        for r in cf_criteria
        if r.get("expected_runtime_flip")
    ]
    if not flipped:
        return None

    grade_unchanged = expected_short == official_short
    missing_pass = [
        str(r.get("criteria_level"))
        for r in cf_criteria
        if _short_level(str(r.get("criteria_level") or "")).startswith("P")
        and not r.get("achieved")
    ]

    return {
        "version": 1,
        "official_grade_label_ar": OFFICIAL_GRADE_LABEL_AR,
        "expected_grade_label_ar": EXPECTED_GRADE_LABEL_AR,
        "disclaimer_ar": EXPECTED_RUNTIME_DISCLAIMER_AR,
        "official_btec_grade": official_short,
        "official_btec_grade_label": f"BTEC {official_short}",
        "expected_btec_grade": expected_short,
        "expected_btec_grade_label": f"BTEC {expected_short}",
        "criteria_flipped_advisory": flipped,
        "grade_unchanged": grade_unchanged,
        "missing_pass_after_runtime_flip": missing_pass,
        "advisory_only": True,
    }


def attach_expected_runtime_grade_display(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    block = build_expected_runtime_grade_display(grading_result)
    if block:
        grading_result["expected_runtime_grade"] = block
    return grading_result
