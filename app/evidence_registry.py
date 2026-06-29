"""Evidence Registry + separated grade display metrics (audit-grade BTEC)."""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.rule_bundle import (
    RUBRIC_RULE_VERSION,
    build_decision_provenance,
    build_decision_provenance_for_execution_mode,
    copy_provenance,
    format_rule_bundle_label,
    resolve_execution_mode,
)


def _criteria_sort_key(level: str) -> Tuple[int, int]:
    lv = (level or "").split(".")[-1].strip().upper()
    tier = lv[:1] if lv else "Z"
    num_m = re.search(r"\d+", lv)
    num = int(num_m.group()) if num_m else 999
    return ({"P": 0, "M": 1, "D": 2}.get(tier, 3), num)


def compute_highest_criterion_achieved(criteria_results: Sequence[Dict[str, Any]]) -> Optional[str]:
    achieved = [
        str(r.get("criteria_level") or "")
        for r in criteria_results
        if isinstance(r, dict) and r.get("achieved") and r.get("criteria_level")
    ]
    if not achieved:
        return None
    achieved.sort(key=_criteria_sort_key)
    return achieved[-1]


def find_evidence_snippets(
    text: str,
    *,
    rule_id: str,
    patterns: Sequence[Tuple[str, re.Pattern]],
    max_snippets: int = 4,
    snippet_chars: int = 80,
) -> Tuple[List[Dict[str, str]], List[str]]:
    """Return (evidence_found, evidence_missing rule keys)."""
    found: List[Dict[str, str]] = []
    missing_keys: List[str] = []
    low = text or ""

    for key, pat in patterns:
        m = pat.search(low)
        if m:
            start = max(0, m.start() - 20)
            end = min(len(low), m.end() + snippet_chars)
            snippet = re.sub(r"\s+", " ", low[start:end]).strip()
            found.append(
                {
                    "rule_key": key,
                    "match": m.group(0)[:120],
                    "snippet": snippet[:200],
                }
            )
        else:
            missing_keys.append(key)

    return found[:max_snippets], missing_keys


def build_criterion_evidence_registry(
    *,
    criteria_level: str,
    rule_id: str,
    result: str,
    evidence_found: Sequence[Dict[str, str]],
    evidence_missing: Sequence[str],
    execution_mode: str,
    reason: str,
    authority: str,
    runtime: Optional[str] = None,
    visual_evidence: Optional[Dict[str, Any]] = None,
    decision_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    prov = copy_provenance(
        decision_provenance or build_decision_provenance_for_execution_mode(execution_mode)
    )
    row: Dict[str, Any] = {
        "criterion": criteria_level,
        "rule_id": rule_id,
        "rule_version": prov.get("rule_version") or RUBRIC_RULE_VERSION,
        "execution_mode": prov.get("execution_mode") or execution_mode,
        "decision_provenance": prov,
        "runtime": runtime or "none",
        "result": result,
        "authority": authority,
        "reason": reason,
        "evidence_found": list(evidence_found),
        "evidence_missing": list(evidence_missing),
    }
    if visual_evidence:
        row["visual_evidence"] = visual_evidence
    return row


def build_grade_display_metrics(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    """Separate UI/PDF metrics — avoids conflating BTEC grade with completion % or highest criterion."""
    criteria = grading_result.get("criteria_results") or []
    achieved_n = sum(1 for r in criteria if isinstance(r, dict) and r.get("achieved"))
    total_n = len(criteria) or 1
    pct = grading_result.get("criteria_score_pct")
    if pct is None:
        pct = grading_result.get("percentage")
    if pct is None:
        pct = round(100.0 * achieved_n / total_n, 1)

    if pct is None:
        pct = round(100.0 * achieved_n / total_n, 1)

    ai_info = grading_result.get("ai_detection_info") or {}
    try:
        ai_pct = float(ai_info.get("score", grading_result.get("ai_likelihood") or 0))
    except (TypeError, ValueError):
        ai_pct = 0.0

    mode = grading_result.get("execution_mode") or resolve_execution_mode(
        grading_result.get("grading_mode")
    )
    provenance = copy_provenance(
        grading_result.get("decision_provenance")
        or build_decision_provenance(grading_result.get("grading_mode"))
    )
    if provenance.get("execution_mode"):
        mode = str(provenance["execution_mode"])
    highest = compute_highest_criterion_achieved(criteria)
    btec = str(grading_result.get("grade_level") or "U").strip().upper()
    if btec and btec[0] in "DMPU":
        btec_short = btec[0]
    else:
        btec_short = "U"

    inst_res = grading_result.get("institutional_resolution") or {}
    inst_btec = str(inst_res.get("btec_grade") or btec_short).strip().upper()
    if inst_btec and inst_btec[0] in "DMPU":
        inst_btec_short = inst_btec[0]
    else:
        inst_btec_short = btec_short

    inconclusive = [
        str(r.get("criteria_level"))
        for r in criteria
        if isinstance(r, dict) and r.get("verdict_status") == "inconclusive"
    ]

    visual_block: Dict[str, Any] = {}
    ves = grading_result.get("visual_evidence_summary")
    if isinstance(ves, dict):
        visual_block = {
            "images_found": ves.get("images_found", 0),
            "images_submitted": ves.get("images_submitted", 0),
            "images_analyzed": ves.get("images_analyzed", 0),
            "images_used_in_decision": ves.get("images_used_in_decision", 0),
            "video_keyframes_found": ves.get("video_keyframes_found", 0),
            "video_keyframes_analyzed": ves.get("video_keyframes_analyzed", 0),
            "video_keyframes_used_in_decision": ves.get("video_keyframes_used_in_decision", 0),
            "vision_status_ar": ves.get("vision_status_ar", ""),
            "vision_error": ves.get("vision_error", ""),
        }
        vk_meta = grading_result.get("basic_video_keyframes_meta") or {}
        if vk_meta.get("frames_per_video"):
            visual_block["video_keyframes_per_video"] = vk_meta.get("frames_per_video")

    out: Dict[str, Any] = {
        "final_btec_grade": inst_btec_short,
        "final_btec_grade_label": f"BTEC {inst_btec_short}",
        "institutional_btec_grade": inst_btec_short,
        "institutional_grade_label_ar": "التقدير المعتمد",
        "criteria_score_pct": round(float(pct), 1),
        "criteria_score_label_ar": "نسبة المعايير",
        "highest_criterion_achieved": highest,
        "highest_criterion_label_ar": (
            f"أعلى معيار متحقق: {highest}" if highest else "لا يوجد معيار متحقق"
        ),
        "criteria_completion_pct": round(float(pct), 1),
        "criteria_achieved_count": achieved_n,
        "criteria_total_count": total_n,
        "grade_score_divergence": inst_btec_short == "U" and float(pct) >= 50,
        "ai_risk_pct": round(ai_pct, 1),
        "ai_risk_advisory": True,
        "execution_mode": mode,
        "rule_version": provenance.get("rule_version") or RUBRIC_RULE_VERSION,
        "decision_provenance": provenance,
        "rule_bundle_label": format_rule_bundle_label(provenance),
        "inconclusive_criteria": inconclusive,
    }
    if visual_block:
        out["visual_evidence"] = visual_block
    ef = grading_result.get("evidence_fingerprint")
    if isinstance(ef, dict) and ef.get("evidence_hash"):
        out["evidence_fingerprint"] = dict(ef)

    try:
        from app.expected_runtime_grade import build_expected_runtime_grade_display

        erg = build_expected_runtime_grade_display(grading_result)
        if erg:
            out["expected_runtime_grade"] = erg
            out["official_grade_label_ar"] = erg.get("official_grade_label_ar")
            out["expected_grade_label_ar"] = erg.get("expected_grade_label_ar")
    except Exception:
        pass

    return out


def attach_evidence_registry_and_metrics(
    grading_result: Dict[str, Any],
    *,
    grading_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """Aggregate per-criterion registries + display metrics onto grading_result."""
    provenance = copy_provenance(
        grading_result.get("decision_provenance")
        or build_decision_provenance(grading_mode or grading_result.get("grading_mode"))
    )
    mode = provenance.get("execution_mode") or resolve_execution_mode(
        grading_mode or grading_result.get("grading_mode")
    )
    grading_result["decision_provenance"] = provenance
    grading_result["execution_mode"] = mode
    grading_result["rule_version"] = provenance.get("rule_version") or RUBRIC_RULE_VERSION

    registries: List[Dict[str, Any]] = []
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        reg = cr.get("evidence_registry")
        if isinstance(reg, dict):
            if not reg.get("decision_provenance"):
                reg["decision_provenance"] = copy_provenance(provenance)
            registries.append(reg)

    evidence_registry: Dict[str, Any] = {
        "rule_version": provenance.get("rule_version") or RUBRIC_RULE_VERSION,
        "execution_mode": mode,
        "decision_provenance": copy_provenance(provenance),
        "criteria": registries,
    }
    ves = grading_result.get("visual_evidence_summary")
    if isinstance(ves, dict):
        evidence_registry["visual_evidence_summary"] = ves
    grading_result["evidence_registry"] = evidence_registry
    grading_result["grade_display_metrics"] = build_grade_display_metrics(grading_result)
    try:
        from app.evidence_fingerprint import attach_evidence_fingerprint

        attach_evidence_fingerprint(grading_result)
    except Exception:
        pass
    return grading_result
