"""
Institutional grade resolution — evidence → meaningful classification (no new AI).

Does not replace BTEC criterion adjudication; adds display bands, runtime summaries,
and reviewer-facing outcomes so submissions are not shown as bare "U" when evidence exists.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

from app.btec_grade_resolution import determine_grade_level, parse_btec_grade_short

_OUTCOME_LABELS_AR = {
    "Distinction": "تميز (Distinction)",
    "Merit": "جيد جداً (Merit)",
    "Pass": "نجاح (Pass)",
    "Referral": "إحالة للمراجعة (Referral)",
    "Partial": "جزئي — أدلة غير مكتملة (Partial)",
    "Unclassified": "غير مصنف (Unclassified)",
}

_EVIDENCE_TIER_AR = {
    "A": "A — runtime verified (استشاري)",
    "B": "B — export/build verified",
    "C": "C — static inference — مراجعة examiner",
    "D": "D — incomplete/corrupted — تقييم يدوي معزّز",
}


def build_runtime_resolution_summary(
    *,
    observation: Optional[Dict[str, Any]] = None,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Structured runtime outcome — replaces vague 'failed' when smoke actually ran."""
    obs = observation or {}
    inv = inventory or {}
    exe = inv.get("executable_artifacts") or {}
    legacy = (obs.get("platform_analyses") or [{}])[0]
    legacy_sig = legacy.get("signals") or {}
    legacy_obs = legacy_sig.get("legacy_observation") or obs.get("legacy_observation") or {}
    godot_smoke = (obs.get("signals") or {}).get("pck_smoke") or legacy_sig.get("pck_smoke")
    promotion = obs.get("runtime_evidence_promotion") or {}
    if not promotion:
        try:
            from app.runtime_evidence_promotion import assess_runtime_evidence_promotion

            promotion = assess_runtime_evidence_promotion(obs, inv)
        except Exception:
            promotion = {}

    runtime_observed = bool(
        obs.get("runtime_observed")
        or legacy_obs.get("runtime_observed")
        or exe.get("runtime_observed")
    )
    runtime_verified = bool(
        obs.get("runtime_verified")
        or legacy_obs.get("runtime_verified")
        or exe.get("runtime_verified")
        or promotion.get("partial_runtime_verified")
        or obs.get("partial_runtime_verified")
    )
    partial_verified = bool(
        promotion.get("partial_runtime_verified")
        or obs.get("partial_runtime_verified")
    )
    engine = obs.get("engine") or "unknown"
    status = obs.get("status") or "unavailable"
    crash = bool(obs.get("crash_detected") or legacy_obs.get("crash_detected"))
    freeze = bool(obs.get("freeze_possible") or legacy_obs.get("freeze_possible"))
    screenshots = obs.get("runtime_screenshots") or legacy_obs.get("runtime_screenshots") or []
    shot_ok = sum(
        1 for s in screenshots
        if isinstance(s, dict) and s.get("status") == "captured"
    )
    gameplay_candidates = int(promotion.get("gameplay_candidate_count") or 0)
    if not gameplay_candidates and shot_ok:
        gameplay_candidates = sum(
            1
            for s in screenshots
            if isinstance(s, dict)
            and s.get("visual_state") == "gameplay_candidate"
            and s.get("status") == "captured"
        )

    gameplay_sem = {}
    try:
        from app.gameplay_semantic_verification import assess_gameplay_semantics

        gameplay_sem = assess_gameplay_semantics(obs, inventory=inv)
    except Exception:
        gameplay_sem = {}

    outcomes: List[str] = []
    if status == "gated":
        outcomes.append("runtime_gated_by_governance")
        label_ar = "معطّل بحكم الحوكمة — ليس عطلاً تقنياً"
        confidence = "none"
    elif not exe.get("files") and not inv.get("runtime_artifacts", {}).get("executables_detected"):
        outcomes.append("no_executable_detected")
        label_ar = "لا ملف تنفيذي للملاحظة"
        confidence = "none"
    elif partial_verified or (runtime_observed and shot_ok >= 2):
        outcomes.append("executable_launched")
        outcomes.append("stable_execution_observed")
        if shot_ok:
            outcomes.append("runtime_screenshots_captured")
        if gameplay_candidates:
            outcomes.append("gameplay_evidence_partial")
        outcomes.append("institutional_verification_incomplete")
        label_ar = promotion.get("summary_ar") or (
            "تشغيل مستقر — أدلة gameplay جزئية (تحقق مؤسسي غير مكتمل — مراجعة examiner)"
        )
        confidence = "medium_high" if gameplay_candidates else "medium"
    elif runtime_verified and engine in ("godot", "legacy_exe"):
        outcomes.extend(["executable_launched", "godot_engine_session"])
        label_ar = "تشغيل Godot — ملاحظة L4 (ليست verification مؤسسية)"
        confidence = "medium_high"
    elif status in ("failed", "crashed", "timeout") and (
        runtime_observed or godot_smoke or legacy_obs.get("smoke_result")
    ):
        outcomes.append("executable_launched")
        outcomes.append("partial_gameplay_or_smoke_incomplete")
        if crash:
            outcomes.append("possible_crash_observed")
        elif freeze:
            outcomes.append("freeze_possible")
        else:
            outcomes.append("watchdog_or_window_ended_safely")
        label_ar = "تشغيل جزئي — جلسة L4 غير مكتملة (ليست فشل النظام)"
        confidence = "low_medium"
    elif runtime_observed and engine == "legacy_exe":
        outcomes.append("executable_launched")
        if shot_ok:
            outcomes.append("runtime_screenshots_captured")
        if crash:
            outcomes.append("possible_crash_observed")
        elif freeze:
            outcomes.append("freeze_possible")
        else:
            outcomes.append("smoke_window_completed")
        label_ar = "تشغيل جزئي — smoke/L4 (ليست verification مؤسسية)"
        confidence = "medium"
    elif godot_smoke and godot_smoke.get("success"):
        outcomes.extend(["godot_main_pack_smoke", "pck_observed"])
        label_ar = "فحص PCK عبر Godot — ملاحظة استشارية"
        confidence = "medium"
    elif runtime_observed:
        outcomes.append("partial_runtime_observed")
        label_ar = "ملاحظة runtime جزئية — مراجعة examiner مطلوبة"
        confidence = "low_medium"
    elif status == "completed":
        outcomes.append("static_or_structural_only")
        label_ar = "تحليل ساكن/هيكلي — دون تشغيل كامل"
        confidence = "low"
    else:
        outcomes.append("runtime_not_observed")
        label_ar = "لم تُسجَّل ملاحظة تشغيل"
        confidence = "none"

    verification_level = str(gameplay_sem.get("verification_level") or "none")
    if verification_level != "none":
        outcomes.append(f"gameplay_verification_{verification_level.lower()}")
    if gameplay_sem.get("progression_missing"):
        outcomes.append("progression_missing")
        label_ar = "تشغيل موجود لكن progression غير مُثبت — التحقق المؤسسي غير مكتمل"
        confidence = "low_medium"
    if gameplay_sem.get("loop_incomplete"):
        outcomes.append("gameplay_loop_incomplete")
        label_ar = "حلقة اللعب غير مكتملة وظيفيًا — مراجعة examiner إلزامية"
        confidence = "low_medium"
    if gameplay_sem.get("gameplay_loop_complete"):
        outcomes.append("gameplay_loop_complete")
        label_ar = "تم رصد حلقة لعب كاملة وظيفيًا (L5 جزئي/مؤسسي)"
        confidence = "high"

    return {
        "version": 1,
        "engine": engine,
        "status": status,
        "outcomes": outcomes,
        "summary_ar": label_ar,
        "runtime_observed": runtime_observed,
        "runtime_verified": runtime_verified,
        "partial_runtime_verified": partial_verified,
        "gameplay_candidate_frames": gameplay_candidates,
        "runtime_evidence_promotion": promotion,
        "institutional_confidence": confidence,
        "screenshot_count": shot_ok,
        "gameplay_semantic": gameplay_sem,
        "gameplay_findings_ar": gameplay_sem.get("findings_ar") or [],
        "gameplay_verification_level": verification_level,
        "advisory_only": True,
        "not_institutional_verification_ar": (
            "هذه الملاحظات استشارية — لا تُعدّ إثباتاً مؤسسياً أن اللعبة تحقق معايير BTEC."
        ),
    }


def resolve_rubric_outcomes(criteria: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Map criterion achievements to rubric bands (no new AI)."""
    p_ach = m_ach = d_ach = p_tot = m_tot = d_tot = 0
    for c in criteria:
        if not isinstance(c, dict):
            continue
        lv = str(c.get("criteria_level") or c.get("level") or "").upper()
        achieved = bool(c.get("achieved"))
        band = ""
        if re.search(r"\.P\d|(^|[^A-Z])P\d", lv):
            band = "P"
        elif re.search(r"\.M\d|(^|[^A-Z])M\d", lv):
            band = "M"
        elif re.search(r"\.D\d|(^|[^A-Z])D\d", lv):
            band = "D"
        if band == "P":
            p_tot += 1
            if achieved:
                p_ach += 1
        elif band == "M":
            m_tot += 1
            if achieved:
                m_ach += 1
        elif band == "D":
            d_tot += 1
            if achieved:
                d_ach += 1

    if d_tot and d_ach == d_tot and m_tot and m_ach == m_tot and p_tot and p_ach == p_tot:
        band = "Distinction"
    elif m_tot and m_ach == m_tot and p_tot and p_ach == p_tot:
        band = "Merit"
    elif p_tot and p_ach == p_tot:
        band = "Pass"
    elif p_ach or m_ach or d_ach:
        band = "Referral"
    else:
        band = "Unclassified"

    return {
        "pass_achieved": p_ach,
        "pass_total": p_tot,
        "merit_achieved": m_ach,
        "merit_total": m_tot,
        "distinction_achieved": d_ach,
        "distinction_total": d_tot,
        "rubric_band": band,
    }


def resolve_institutional_classification(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    confidence_tier: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Map collected evidence to institutional outcome band + display grade."""
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    criteria = grading_result.get("criteria_results") or []
    achieved = sum(1 for c in criteria if isinstance(c, dict) and c.get("achieved"))
    total = len(criteria)
    pct = float(grading_result.get("percentage") or 0)
    # SSOT: grade_level is set by btec_criteria_governance / batch_grader pipeline.
    btec = parse_btec_grade_short(str(grading_result.get("grade_level") or ""))
    if not btec or btec == "U":
        btec = determine_grade_level(criteria)

    obs = inv.get("runtime_observation_report") or {}
    runtime_res = build_runtime_resolution_summary(observation=obs, inventory=inv)
    tier = confidence_tier or obs.get("confidence_tier") or {}
    if isinstance(tier, dict):
        tier = dict(tier)
    else:
        tier = {}

    _promo: Dict[str, Any] = {}
    try:
        from app.runtime_evidence_promotion import (
            apply_confidence_tier_floor,
            assess_runtime_evidence_promotion,
        )

        _promo = assess_runtime_evidence_promotion(obs, inv)
        tier = apply_confidence_tier_floor(tier, _promo)
    except Exception:
        pass

    cov = inv.get("extraction_coverage") or {}
    weak_src = bool(cov.get("weak_analysis_risk"))
    has_pck_src = any(
        (f or {}).get("source_kind") == "godot_pck_embedded"
        for f in (inv.get("source_code") or {}).get("files") or []
    )
    has_exe = bool(
        (inv.get("executable_artifacts") or {}).get("files")
        or (inv.get("runtime_artifacts") or {}).get("executables_detected")
    )
    has_doc = bool((inv.get("documentation") or {}).get("files"))

    tier_code = str(tier.get("tier") or "").upper()
    if not tier_code and runtime_res.get("runtime_verified"):
        tier_code = "A"
    elif not tier_code and runtime_res.get("runtime_observed"):
        tier_code = "B"
    elif not tier_code and (has_exe or has_doc):
        tier_code = "C"

    rubric = resolve_rubric_outcomes(criteria)

    if btec == "D":
        outcome_band = "Distinction"
    elif btec == "M":
        outcome_band = "Merit"
    elif btec == "P":
        outcome_band = "Pass"
    elif achieved > 0 and pct >= 40 and (has_exe or has_doc):
        outcome_band = "Referral"
    elif runtime_res.get("partial_runtime_verified") or _promo.get("strong_partial"):
        outcome_band = "Partial"
    elif (
        achieved > 0
        or runtime_res.get("runtime_observed")
        or has_pck_src
        or (has_exe and has_doc)
        or tier_code in ("A", "B")
    ):
        outcome_band = "Partial"
    else:
        outcome_band = "Unclassified"

    # Confidence tier overlay (A–D) without changing BTEC letter
    if tier_code == "A" and outcome_band in ("Referral", "Partial", "Unclassified"):
        outcome_band = "Partial" if achieved else "Referral"
    elif tier_code == "B" and outcome_band in ("Unclassified", "Referral") and (
        has_exe or runtime_res.get("runtime_observed")
    ):
        outcome_band = "Partial"
    elif tier_code == "C" and outcome_band == "Unclassified" and (has_doc or has_exe):
        outcome_band = "Partial"
    elif tier_code == "D" and outcome_band == "Unclassified" and achieved > 0:
        outcome_band = "Referral"

    if rubric.get("rubric_band") in ("Distinction", "Merit", "Pass"):
        outcome_band = rubric["rubric_band"]

    display_grade = btec if btec in ("D", "M", "P") else outcome_band[0] if outcome_band != "Unclassified" else "U"
    display_ar = _OUTCOME_LABELS_AR.get(outcome_band, outcome_band)
    if btec in ("D", "M", "P"):
        display_ar = f"{display_ar} — معيار BTEC: {btec}"

    referral_reasons: List[str] = []
    if outcome_band == "Referral":
        if not runtime_res.get("runtime_verified"):
            referral_reasons.append("runtime_not_institutionally_verified")
        if weak_src and not has_pck_src:
            referral_reasons.append("incomplete_source_coverage")
        if achieved < total:
            referral_reasons.append("partial_criteria_achievement")
    if weak_src and not has_pck_src:
        referral_reasons.append("source_coverage_advisory")

    evidence_tier_ar = _EVIDENCE_TIER_AR.get(tier_code, "") if tier_code else ""

    return {
        "version": 1,
        "btec_grade": btec,
        "outcome_band": outcome_band,
        "display_grade": display_grade,
        "display_grade_ar": display_ar,
        "confidence_tier": tier_code or None,
        "evidence_tier_ar": evidence_tier_ar,
        "rubric_resolution": rubric,
        "percentage": pct,
        "criteria_achieved": achieved,
        "criteria_total": total,
        "runtime_resolution": runtime_res,
        "referral_reasons": referral_reasons,
        "examiner_signoff_required": bool(
            tier.get("examiner_signoff_required")
            or outcome_band in ("Referral", "Partial", "Unclassified")
            or (weak_src and not has_pck_src)
        ),
        "missing_source_advisory_only": weak_src and not has_pck_src,
        "summary_ar": (
            f"تصنيف مؤسسي: {display_ar}. "
            f"تحقق {achieved}/{total} معياراً ({pct:.0f}%). "
            + (f"ثقة الأدلة: {evidence_tier_ar}. " if evidence_tier_ar else "")
            + f"Runtime: {runtime_res.get('summary_ar', '—')}"
        ),
    }


def attach_institutional_grade_resolution(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Attach resolution block and UI-friendly fields to grading snapshot."""
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    tier = obs.get("confidence_tier") or grading_result.get("confidence_tier")

    resolution = resolve_institutional_classification(
        grading_result,
        artifact_inventory=inv,
        confidence_tier=tier if isinstance(tier, dict) else None,
    )
    grading_result["institutional_resolution"] = resolution
    grading_result["institutional_grade_display"] = resolution.get("display_grade_ar")
    grading_result["runtime_resolution_summary"] = resolution.get("runtime_resolution")

    # Enrich explainability without changing protected criterion scores
    layer = grading_result.setdefault("explainability_layer", {})
    if not isinstance(layer, dict):
        layer = {}
        grading_result["explainability_layer"] = layer

    gov = layer.get("governance_intent") or inv.get("governance_intent") or {}
    if isinstance(gov, dict):
        rt = resolution.get("runtime_resolution") or {}
        gov = dict(gov)
        gov["runtime_resolution_ar"] = rt.get("summary_ar", "")
        gov["gameplay_verification_level"] = rt.get("gameplay_verification_level", "")
        gov["gameplay_findings_ar"] = rt.get("gameplay_findings_ar") or []
        gov["institutional_outcome_ar"] = resolution.get("display_grade_ar", "")
        if rt.get("runtime_observed"):
            gov["runtime_execution_ar"] = rt.get("summary_ar", gov.get("runtime_execution_ar", ""))
            gov["not_a_system_failure_ar"] = (
                "تمت ملاحظة runtime — التقييم الاستشاري لا يعادل تحقق المعيار تلقائياً."
            )
        layer["governance_intent"] = gov
        inv["governance_intent"] = gov

    notes = grading_result.get("reviewer_notes") or ""
    inst_note = resolution.get("summary_ar", "")
    if inst_note and inst_note not in notes:
        grading_result["reviewer_notes"] = (notes + "\n\n[Institutional resolution]\n" + inst_note).strip()

    return grading_result
