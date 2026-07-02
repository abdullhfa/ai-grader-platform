"""
Pearson BTEC Jordan — PRO-only institutional package (grading_mode=deep).

BASIC (fast) must never import or call these functions.

Principles encoded:
  - Achievement requires linked evidence, not runnable code alone.
  - P/M/D cannot rest on AI assertion without artifacts.
  - Technical validation (runtime/files) is separate from academic validation.
  - Full per-criterion audit trail for Internal / External Verification.
"""
from __future__ import annotations

import copy
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.btec_criteria_governance import (
    _band,
    _demote_row,
    _short_level,
    apply_btec_awardability,
    compute_criteria_score_pct,
)

PEARSON_PACKAGE_VERSION = "pro_btec_pearson_v3"

# Pearson PRO evidence weight model (informational — supports criterion_score stability).
PRO_EVIDENCE_WEIGHTS: Dict[str, int] = {
    "runtime": 30,
    "source_code": 40,
    "design_document": 20,
    "evaluation": 10,
}

_AUTHENTICITY_AUTO_FAIL_THRESHOLD = 95  # only flag review; never auto-fail below this alone

# Jordan ministry / Pearson commonly approved tooling (detection hints).
JORDAN_APPROVED_SOFTWARE: Dict[str, Dict[str, Any]] = {
    "python": {"extensions": (".py",), "labels_ar": ("Python",)},
    "visual_studio": {"extensions": (".cs", ".sln", ".vcxproj"), "labels_ar": ("Visual Studio / C#",)},
    "android_studio": {"extensions": (".kt", ".java", ".gradle", ".apk"), "labels_ar": ("Android Studio",)},
    "flutter": {"extensions": (".dart",), "labels_ar": ("Flutter",)},
    "java": {"extensions": (".java",), "labels_ar": ("Java",)},
    "kotlin": {"extensions": (".kt",), "labels_ar": ("Kotlin",)},
    "unity": {"markers": ("unity", ".unity", "assembly-csharp"), "labels_ar": ("Unity",)},
    "godot": {"markers": ("godot", "project.godot", ".gd", ".pck"), "labels_ar": ("Godot",)},
    "gamemaker": {"markers": (".gml", ".yyp", "gamemaker"), "labels_ar": ("GameMaker",)},
    "scratch": {"markers": (".sb3", ".sb2", "scratch"), "labels_ar": ("Scratch",)},
    "unreal": {"markers": (".uproject", "unreal"), "labels_ar": ("Unreal",)},
    "cisco_packet_tracer": {"markers": (".pkt", "packet tracer"), "labels_ar": ("Cisco Packet Tracer",)},
    "visio": {"markers": (".vsdx", ".vsd"), "labels_ar": ("Visio",)},
    "gimp": {"markers": (".xcf",), "labels_ar": ("GIMP",)},
    "inkscape": {"markers": (".svg",), "labels_ar": ("Inkscape",)},
    "vmware": {"markers": (".vmx", ".vmdk"), "labels_ar": ("VMware",)},
    "virtualbox": {"markers": (".vbox", ".vdi"), "labels_ar": ("VirtualBox",)},
    "google_colab": {"markers": ("colab", ".ipynb"), "labels_ar": ("Google Colab / Jupyter",)},
}

BAND_ACCEPTED_EVIDENCE_AR: Dict[str, List[str]] = {
    "P": [
        "تقرير تحليل / Word أو PDF",
        "مخططات أو جداول توضيحية",
        "دراسة حالة أو سيناريو موثّق",
        "كود مصدر أو حزمة مشروع",
        "لقطات تشغيل أو فيديو قصير",
    ],
    "M": [
        "تبرير قرارات التصميم (مقارنة بدائل)",
        "تحليل متوسط العمق مع أدلة مرفقة",
        "توثيق اختبار أو playtest",
    ],
    "D": [
        "تقييم نقدي معمّق للفعالية والقيود",
        "تحليل تأثير على المستخدم/العميل",
        "أدلة تتجاوز الحد الأدنى لـ Pass و Merit",
    ],
}

_RUNTIME_ONLY_AUTHORITIES = frozenset(
    {
        "RUNTIME_OBSERVATION_L4",
        "RUNTIME_INSUFFICIENT",
        "RUNTIME_DEFER_DELIVERABLE",
        "RUNTIME_VALIDATION",
        "RUNTIME_OBSERVATION",
    }
)

_EXECUTION_SHORT = frozenset({"P5", "P6", "P7", "M3"})

_PREREQUISITE_GATE_AR = {
    "missing_pass_criteria": "محجوب — C.P5/C.P6 لم يُتحققا (Prerequisite)",
    "missing_merit_criteria": "محجوب — معايير Merit ناقصة (Prerequisite)",
}


def _compact_gate_reason(cr: Dict[str, Any], *, gate_summary: str) -> str:
    block_code = str(cr.get("award_block_reason") or "")
    if block_code in _PREREQUISITE_GATE_AR:
        return _PREREQUISITE_GATE_AR[block_code]
    return (
        str(cr.get("award_block_reason_ar") or "")
        or str(cr.get("governance_adjustment_ar") or "")
        or (gate_summary if cr.get("runtime_gate_block") else "")
        or ""
    )


_AI_ASSERTION_ONLY = frozenset(
    {
        "",
        "AI_ASSERTION",
        "MODEL_ASSERTION",
        "LLM_ONLY",
    }
)


def _levels_match(stored: str, target: str) -> bool:
    a = _short_level(stored)
    b = _short_level(target)
    return bool(a and b and a == b)


def _gate_row_for_level(
    gate_report: Dict[str, Any], level: str
) -> Optional[Dict[str, Any]]:
    for row in gate_report.get("per_criterion") or []:
        if isinstance(row, dict) and _levels_match(
            str(row.get("criteria_level") or ""), level
        ):
            return row
    return None


def build_evidence_mapping_matrix(
    grading_criteria: Sequence[Dict[str, Any]],
    gate_report: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Per-criterion accepted vs present evidence (Pearson Evidence Mapping)."""
    gate_report = gate_report or {}
    matrix: List[Dict[str, Any]] = []
    for crit in grading_criteria or []:
        if not isinstance(crit, dict):
            continue
        level = str(crit.get("criteria_level") or "")
        band = _band(level) or "P"
        gate_row = _gate_row_for_level(gate_report, level) or {}
        required = list(gate_row.get("required_artifacts") or [])
        missing = list(gate_row.get("missing_artifacts") or [])
        matrix.append(
            {
                "criteria_level": level,
                "band": band,
                "accepted_evidence_types_ar": list(BAND_ACCEPTED_EVIDENCE_AR.get(band, [])),
                "required_artifact_keys": required,
                "missing_artifact_keys": missing,
                "evidence_sufficient_for_award": not missing,
                "pearson_rule_ar": (
                    "لا يُمنح المعيار دون دليل مرتبط يثبت تحقق Learning Outcome — "
                    "التشغيل التقني وحده لا يكفي."
                ),
            }
        )
    return matrix


def detect_jordan_approved_software(
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    submission_paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    """Map submission to ministry-approved tooling categories (PRO audit)."""
    inv = artifact_inventory or {}
    joined = " ".join(submission_paths or []).lower()
    for raw in inv.get("intake_relative_paths") or []:
        joined += " " + str(raw).lower()
    profile = inv.get("project_profile") or inv.get("ultra_light_project_profile") or {}
    for eng in profile.get("engines_detected") or profile.get("project_types") or []:
        joined += " " + str(eng).lower()

    detected: List[str] = []
    for key, spec in JORDAN_APPROVED_SOFTWARE.items():
        hit = False
        for ext in spec.get("extensions") or ():
            if ext.lower() in joined:
                hit = True
                break
        if not hit:
            for marker in spec.get("markers") or ():
                if str(marker).lower() in joined:
                    hit = True
                    break
        if hit:
            detected.append(key)

    return {
        "detected_tools": detected,
        "detected_labels_ar": [
            lab
            for key in detected
            for lab in JORDAN_APPROVED_SOFTWARE.get(key, {}).get("labels_ar") or ()
        ],
        "grading_rules_note_ar": (
            "تختلف قواعد التصحيح حسب نوع المشروع (لعبة / شبكة / تطبيق / توثيق) — "
            "يُفصل التحقق التقني عن التحقق الأكاديمي في PRO."
        ),
    }


def build_technical_validation_summary(
    grading_result: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    gate = grading_result.get("evidence_completeness_gate") or {}
    assets = gate.get("assets_detected") or {}
    rt = inv.get("runtime_observation_report") or {}
    rv = inv.get("runtime_validation") or {}
    try:
        from app.pro_engine_gameplay_governance import (
            build_runtime_telemetry,
            is_structure_only_runtime,
        )

        telemetry = build_runtime_telemetry(inv)
        structure_only = is_structure_only_runtime(inv)
        launch_ok = telemetry.get("game_launch_attempted") is True
        smoke_ok = (rv.get("functional_smoke") or {}).get("functional_smoke_pass") is True
        runtime_verified = bool(
            not structure_only
            and launch_ok
            and smoke_ok
            and not telemetry.get("crash")
        )
    except Exception:
        structure_only = False
        runtime_verified = bool(
            rt.get("runtime_verified")
            and (rv.get("functional_smoke") or {}).get("functional_smoke_pass") is True
        )
        telemetry = {}
    return {
        "code_present": bool(assets.get("source_code") or inv.get("has_source_code_artifacts")),
        "executable_present": bool(assets.get("executable") or inv.get("has_executable_artifacts")),
        "documentation_present": bool(assets.get("word_pdf")),
        "runtime_verified": runtime_verified,
        "runtime_structure_only": structure_only,
        "runtime_telemetry": telemetry,
        "runtime_status": rt.get("status") or rv.get("status"),
        "summary_ar": (
            "التحقق التقني: تشغيل حقيقي (نافذة/مشهد) وليس فحص ملفات فقط — "
            "لا يعادل تحقيق معيار Pass/Merit/Distinction أكاديمياً."
        ),
    }


def build_academic_validation_summary(
    grading_result: Dict[str, Any],
) -> Dict[str, Any]:
    criteria = grading_result.get("criteria_results") or []
    achieved = [r for r in criteria if isinstance(r, dict) and r.get("achieved")]
    awardable = [r for r in criteria if isinstance(r, dict) and r.get("awardable")]
    blocked = [
        str(r.get("criteria_level"))
        for r in criteria
        if isinstance(r, dict)
        and r.get("achieved")
        and not r.get("awardable")
    ]
    award = grading_result.get("btec_institutional_award") or {}
    return {
        "criteria_achieved_count": len(achieved),
        "criteria_awardable_count": len(awardable),
        "achieved_not_awardable_levels": blocked,
        "institutional_grade": award.get("institutional_grade") or grading_result.get("grade_level"),
        "summary_ar": (
            "التحقق الأكاديمي: تحقق Learning Outcomes ومعايير P/M/D بأدلة نصية/توثيقية — "
            "يُدمج مع التقني ولا يُستبدل به."
        ),
    }


def build_authenticity_summary(grading_result: Dict[str, Any]) -> Dict[str, Any]:
    ai = grading_result.get("ai_detection") or {}
    score = int(grading_result.get("ai_likelihood") or ai.get("score") or 0)
    risk = str(ai.get("risk_classification") or "")
    plag = grading_result.get("plagiarism_summary") or {}
    max_sim = plag.get("max_similarity")
    susp = int(plag.get("suspicious_count") or 0)
    plagiarism_confirmed = bool(
        (max_sim is not None and float(max_sim) >= 26.0) or susp > 0
    )

    if plagiarism_confirmed:
        warning = "high"
        warning_ar = "تحذير: تشابه مرتفع أو مطابقات انتحال — مراجعة IV/EV إلزامية."
        action_ar = "مراجعة بشرية للانتحال — لا إلغاء تلقائي للمعايير."
    elif score >= 70:
        warning = "medium"
        warning_ar = "تحذير: احتمال مساعدة ذكاء اصطناعي مرتفع — لا يكفي وحده لرفض المعيار."
        action_ar = "مراجعة توثيق الطالب ومقارنة الأقران."
    elif score >= 40:
        warning = "low"
        warning_ar = "ملاحظة أصالة: احتمال AI متوسط."
        action_ar = "لا إجراء إلزامي — يُسجّل في حزمة IV."
    else:
        warning = "none"
        warning_ar = "لا تحذير أصالة جوهري."
        action_ar = "متابعة عادية."

    return {
        "ai_likelihood_pct": score,
        "ai_risk_classification": risk,
        "plagiarism_max_similarity": max_sim,
        "plagiarism_suspicious_count": susp,
        "authenticity_warning": warning,
        "authenticity_warning_ar": warning_ar,
        "recommended_action_ar": action_ar,
        "automatic_fail_prohibited": True,
        "plagiarism_requires_human_review": plagiarism_confirmed,
        "confidence_note_ar": (
            "Pearson PRO: ai_likelihood تحذير فقط — لا automatic_fail إلا بأدلة انتحال مؤكدة."
        ),
    }


def _inventory_evidence_flags(inv: Dict[str, Any]) -> Dict[str, bool]:
    has_docs = bool((inv.get("documentation") or {}).get("files"))
    joined = str(inv.get("intake_relative_paths") or inv).lower()
    return {
        "runtime": bool(
            (inv.get("runtime_observation_report") or {}).get("runtime_verified")
            or inv.get("has_executable_artifacts")
        ),
        "source_code": bool(inv.get("has_source_code_artifacts")),
        "design_document": has_docs,
        "evaluation": has_docs
        and any(k in joined for k in ("review", "evaluat", "تقييم", "مراجعة")),
    }


def _weight_types_for_band(band: str, flags: Dict[str, bool]) -> List[str]:
    types: List[str] = []
    if flags.get("source_code"):
        types.append("source_code")
    if flags.get("runtime"):
        types.append("runtime")
    if flags.get("design_document") and band in ("P", "M"):
        types.append("design_document")
    if flags.get("evaluation") or band in ("M", "D"):
        types.append("evaluation")
    if not types:
        if flags.get("design_document"):
            types.append("design_document")
    return types


def apply_evidence_weighting_to_criteria(
    criteria_results: List[Dict[str, Any]],
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> None:
    """Attach evidence_weight breakdown + weighted_evidence_score (0–100) per criterion."""
    inv = artifact_inventory or {}
    flags = _inventory_evidence_flags(inv)
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        band = _band(str(row.get("criteria_level") or "")) or "P"
        types = _weight_types_for_band(band, flags)
        breakdown: Dict[str, int] = {}
        total_w = 0
        score_sum = 0
        for t in types:
            w = PRO_EVIDENCE_WEIGHTS.get(t, 0)
            breakdown[t] = w
            total_w += w
        if total_w > 0:
            score_sum = round(100 * sum(breakdown.values()) / total_w)
        linked = _row_has_linked_evidence(row, None)
        if not linked:
            score_sum = min(score_sum, 40)
        if not row.get("achieved"):
            score_sum = min(score_sum, 35)
        row["evidence_weight"] = breakdown
        row["evidence_weighted_score"] = score_sum
        row["evidence_weight_model_ar"] = (
            "وزن الأدلة: كود 40%، تشغيل 30%، تصميم 20%، تقييم 10% — معلوماتي لـ IV."
        )


def build_evidence_locators_for_criterion(
    row: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    gate_report: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """
    Pearson-style locators: file + section + page/image — not attachment-only.
    """
    locators: List[Dict[str, Any]] = []
    level = str(row.get("criteria_level") or "")

    for cell in row.get("decision_matrix") or []:
        if not isinstance(cell, dict):
            continue
        proof = str(
            cell.get("evidence")
            or cell.get("evidence_ref")
            or cell.get("reason")
            or ""
        ).strip()
        if not proof and not cell.get("met"):
            continue
        locators.append(
            {
                "criterion": level,
                "artifact_file": str(cell.get("source") or cell.get("file") or ""),
                "evidence_section": str(
                    cell.get("section") or cell.get("evidence_section") or ""
                ),
                "page_or_position": cell.get("page") or cell.get("page_or_slide"),
                "image_reference": str(
                    cell.get("image")
                    or cell.get("screenshot")
                    or cell.get("figure")
                    or ""
                ),
                "proof": proof[:500],
                "locator_type": "decision_matrix",
            }
        )

    snap = row.get("academic_evidence_snapshot") or row.get("academic_snapshot") or {}
    if isinstance(snap, dict):
        for doc in (snap.get("documentation_refs") or snap.get("doc_refs") or [])[:5]:
            if isinstance(doc, dict):
                locators.append(
                    {
                        "criterion": level,
                        "artifact_file": doc.get("basename") or doc.get("file") or "",
                        "evidence_section": doc.get("section") or "academic_snapshot",
                        "page_or_position": doc.get("page"),
                        "image_reference": doc.get("image_index") or doc.get("figure"),
                        "proof": str(doc.get("excerpt") or doc.get("proof") or "")[:500],
                        "locator_type": "academic_snapshot",
                    }
                )

    inv = artifact_inventory or {}
    for docf in (inv.get("documentation") or {}).get("files") or []:
        if not isinstance(docf, dict):
            continue
        name = docf.get("name") or docf.get("basename") or ""
        if not name:
            continue
        locators.append(
            {
                "criterion": level,
                "artifact_file": name,
                "evidence_section": "GDD/توثيق مرفق",
                "page_or_position": docf.get("page_estimate") or "مستند كامل",
                "image_reference": "",
                "proof": f"ملف توثيق مرتبط بمعيار {level}",
                "locator_type": "design_document",
            }
        )
        if len(locators) >= 6:
            break

    for exf in (inv.get("executable_artifacts") or {}).get("files") or []:
        if not isinstance(exf, dict):
            continue
        locators.append(
            {
                "criterion": level,
                "artifact_file": exf.get("name") or "",
                "evidence_section": "تشغيل/بناء اللعبة",
                "page_or_position": "runtime",
                "image_reference": "",
                "proof": "ملف تنفيذي — تحقق تقني (لا يعادل تحقق أكاديمي وحده)",
                "locator_type": "runtime",
            }
        )
        break

    gate = gate_report or {}
    for path in gate.get("expanded_paths_sample") or []:
        locators.append(
            {
                "criterion": level,
                "artifact_file": str(path).split("\\")[-1].split("/")[-1],
                "evidence_section": "مسار مُفهرس",
                "page_or_position": path,
                "image_reference": "",
                "proof": "دليل ملف من بوابة الاكتمال",
                "locator_type": "indexed_path",
            }
        )
        if len(locators) >= 10:
            break

    deduped: List[Dict[str, Any]] = []
    seen: set = set()
    for loc in locators:
        key = (
            loc.get("artifact_file"),
            loc.get("evidence_section"),
            loc.get("page_or_position"),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(loc)
    return deduped[:12]


def build_evidence_locators_by_criterion(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    gate = grading_result.get("evidence_completeness_gate") or {}
    out: Dict[str, List[Dict[str, Any]]] = {}
    for row in grading_result.get("criteria_results") or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "")
        locs = build_evidence_locators_for_criterion(
            row,
            artifact_inventory=artifact_inventory,
            gate_report=gate,
        )
        row["evidence_locator"] = locs
        short = _short_level(level)
        out[level] = locs
        out[short] = locs
    return out


def validate_unit_award(
    criteria_results: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """
    Unit-level award validator (Pearson): incomplete Pass blocks Merit/Distinction.
    Complements per-row ``awardable`` from apply_btec_awardability.
    """
    working = copy.deepcopy(criteria_results)
    award = apply_btec_awardability(working)

    p_rows, m_rows, d_rows = [], [], []
    for row in working:
        if not isinstance(row, dict):
            continue
        b = _band(str(row.get("criteria_level") or ""))
        if b == "P":
            p_rows.append(row)
        elif b == "M":
            m_rows.append(row)
        elif b == "D":
            d_rows.append(row)

    missing_pass = [str(r.get("criteria_level")) for r in p_rows if not r.get("achieved")]
    missing_merit = [str(r.get("criteria_level")) for r in m_rows if not r.get("achieved")]
    missing_dist = [str(r.get("criteria_level")) for r in d_rows if not r.get("achieved")]

    all_p = len(p_rows) > 0 and not missing_pass
    all_m = len(m_rows) > 0 and not missing_merit
    all_d = len(d_rows) > 0 and not missing_dist

    merit_unit = all_p and all_m
    distinction_unit = all_p and all_m and all_d
    band = institutional_grade_from_awardable(working)

    if not all_p:
        block_ar = (
            f"لا يُمنح Merit/Distinction على مستوى الوحدة — معايير Pass ناقصة: "
            f"{', '.join(missing_pass)}"
        )
    elif not all_m and any(r.get("achieved") for r in m_rows + d_rows):
        block_ar = (
            f"لا يُمنح Distinction — معايير Merit ناقصة: {', '.join(missing_merit)}"
        )
    elif not all_d and any(r.get("achieved") for r in d_rows):
        block_ar = "معايير Distinction ناقصة على مستوى الوحدة."
    else:
        block_ar = ""

    return {
        "unit_awardable_band": band,
        "merit_unit_awardable": merit_unit,
        "distinction_unit_awardable": distinction_unit,
        "pass_complete": all_p,
        "missing_pass_criteria": missing_pass,
        "missing_merit_criteria": missing_merit,
        "missing_distinction_criteria": missing_dist,
        "unit_block_reason_ar": block_ar,
        "per_criterion_awardability": award,
        "validator_ar": (
            "إذا فشل P4 (مثال) لا يُمنح الطالب Merit/Distinction رسمياً حتى لو حقق M/D أكاديمياً."
        ),
    }


def build_gameplay_validation_summary(
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Gameplay checks for game units — win/lose/scene/save/score (advisory)."""
    inv = artifact_inventory or {}
    obs = inv.get("runtime_observation_report") or {}
    rv = inv.get("runtime_validation") or {}
    gplay = obs.get("gameplay_analysis") or inv.get("gameplay_analysis") or {}
    gvi = inv.get("gameplay_video_inference") or {}

    def _event_observed(event_type: str) -> tuple[bool, str]:
        timeline = gplay.get("timeline") or {}
        events = timeline.get("events") if isinstance(timeline, dict) else timeline
        if isinstance(events, list):
            for ev in events:
                if isinstance(ev, dict) and str(ev.get("type") or "") == event_type:
                    return True, "gameplay_analysis"
        reports = gplay.get("gameplay_reports") or {}
        if event_type == "win_detected" and (reports.get("win") or {}).get("label") == "win_detected":
            return True, "gameplay_reports"
        if event_type == "lose" and (reports.get("lose") or {}).get("label"):
            return True, "gameplay_reports"
        if event_type == "score" and (reports.get("score") or {}).get("label") == "score_hud_detected":
            return True, "gameplay_reports"
        hints = (gvi.get("video_analysis") or {}).get("runtime_hints") or []
        blob = str(hints).lower()
        if event_type == "win_detected" and any(k in blob for k in ("win", "victory", "فوز")):
            return True, "video_hints"
        if event_type == "scene" and any(k in blob for k in ("scene", "level", "مشهد")):
            return True, "video_hints"
        return False, "not_observed"

    win_ok, win_src = _event_observed("win_detected")
    lose_ok, lose_src = _event_observed("lose_detected")
    if not lose_ok:
        lose_ok, lose_src = _event_observed("death_detected")
    scene_ok, scene_src = _event_observed("scene_change_detected")
    if not scene_ok:
        scene_sig = (obs.get("runtime_signal_graph") or {}).get("signals") or {}
        scene_ok = bool(scene_sig.get("mentions_scene") or obs.get("unity_observation_summary"))
        scene_src = "runtime_logs" if scene_ok else scene_src
    save_ok = bool(
        ((obs.get("runtime_signal_graph") or {}).get("signals") or {}).get("mentions_save")
        or any(
            isinstance(u, dict) and u.get("save_load_hint")
            for u in (obs.get("unity_observation_summary") or [])
        )
    )
    save_src = "runtime_logs" if save_ok else "not_observed"
    score_ok, score_src = _event_observed("score_tokens_detected")

    checks = {
        "win_state": {
            "observed": win_ok,
            "source": win_src,
            "note_ar": "فوز/انتصار — مطلوب لمراجعة IV في وحدات الألعاب",
        },
        "lose_state": {
            "observed": lose_ok,
            "source": lose_src,
            "note_ar": "خسارة/موت — دليل على حلقة لعب",
        },
        "scene_transition": {
            "observed": scene_ok,
            "source": scene_src,
            "note_ar": "انتقال مشاهد/مستويات",
        },
        "save_data": {
            "observed": save_ok,
            "source": save_src,
            "note_ar": "حفظ/تحميل بيانات",
        },
        "score_hud": {
            "observed": score_ok,
            "source": score_src,
            "note_ar": "نقاط/واجهة HUD",
        },
    }
    observed_n = sum(1 for c in checks.values() if c.get("observed"))
    try:
        from app.pro_engine_gameplay_governance import (
            assess_playtest_evidence,
            detect_primary_game_engine,
            get_engine_policy,
        )

        engine_id = detect_primary_game_engine(inv)
        policy = get_engine_policy(engine_id)
        playtest = assess_playtest_evidence(inv, gameplay_checks=checks)
        gameplay_validation_passed = bool(
            playtest.get("any_path_satisfied")
            and playtest.get("playtest_paths", {}).get("runtime_gameplay_validated")
        )
        advisory_only = not bool(policy.get("gameplay_validation_required"))
    except Exception:
        engine_id = "unknown"
        policy = {}
        playtest = {}
        gameplay_validation_passed = False
        advisory_only = True

    return {
        "checks": checks,
        "mechanics_observed_count": observed_n,
        "engine_id": engine_id,
        "engine_policy": {
            "gameplay_validation_required": policy.get("gameplay_validation_required"),
            "unity_runtime_validation": policy.get("unity_runtime_validation"),
            "playtest_required": policy.get("playtest_required"),
            "human_review_required": policy.get("human_review_required"),
        },
        "playtest_assessment": playtest,
        "gameplay_validation_passed": gameplay_validation_passed,
        "advisory_only": advisory_only,
        "functional_smoke_pass": (rv.get("functional_smoke") or {}).get(
            "functional_smoke_pass"
        ),
        "summary_ar": (
            playtest.get("summary_ar")
            if playtest.get("summary_ar")
            else (
                f"Gameplay PRO: {observed_n}/5 فحوصات مُلاحظة — "
                "التشغيل لا يمنح C.P6/M/D بدون playtest موثّق."
            )
        ),
    }


def _row_has_linked_evidence(row: Dict[str, Any], gate_row: Optional[Dict[str, Any]]) -> bool:
    if gate_row and gate_row.get("missing_artifacts"):
        return False
    matrix = row.get("decision_matrix")
    if isinstance(matrix, list) and matrix:
        for cell in matrix:
            if isinstance(cell, dict) and cell.get("met") and (
                cell.get("evidence") or cell.get("evidence_ref") or cell.get("source")
            ):
                return True
    det = row.get("deterministic_rubric") or {}
    if det.get("evidence_keys") or det.get("matched_evidence"):
        return True
    if row.get("evidence_refs") or row.get("academic_evidence_snapshot"):
        return True
    return False


def apply_pro_evidence_gate_demotions(
    criteria_results: List[Dict[str, Any]],
    gate_report: Dict[str, Any],
) -> List[str]:
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        level = str(row.get("criteria_level") or "")
        gate_row = _gate_row_for_level(gate_report, level)
        if not gate_row:
            continue
        missing = gate_row.get("missing_artifacts") or []
        if missing:
            _demote_row(
                row,
                "بوابة أدلة Pearson: لا يُمنح المعيار دون الأدلة المطلوبة المرتبطة "
                f"({', '.join(missing)}).",
            )
            row["evidence_gate_blocked"] = True
            changes.append(f"{level}:evidence_gate_missing")
    return changes


def institutional_grade_from_awardable(
    criteria_results: List[Dict[str, Any]],
) -> str:
    """
    Pearson institutional band from ``awardable`` (official grant), not ``achieved`` alone.
    PRO uses this to override ``determine_grade_level`` which only checks achieved.
    """
    def short_level(lv: str) -> str:
        return lv.split(".")[-1] if "." in lv else lv

    p_rows, m_rows, d_rows = [], [], []
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        sl = short_level(str(row.get("criteria_level") or "")).upper()
        if sl.startswith("P"):
            p_rows.append(row)
        elif sl.startswith("M"):
            m_rows.append(row)
        elif sl.startswith("D"):
            d_rows.append(row)

    def _band_met(rows: List[Dict[str, Any]]) -> bool:
        if not rows:
            return False
        return all(
            bool(r.get("awardable")) if "awardable" in r else bool(r.get("achieved"))
            for r in rows
        )

    if _band_met(p_rows) and _band_met(m_rows) and _band_met(d_rows):
        return "D"
    if _band_met(p_rows) and _band_met(m_rows):
        return "M"
    if _band_met(p_rows):
        return "P"
    return "U"


def apply_pro_execution_runtime_cap(
    criteria_results: List[Dict[str, Any]],
    *,
    gate_report: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    C.P5/C.P6/C.P7: smoke/runtime (L4) cannot alone prove BTEC achievement — needs test/doc evidence.
    """
    changes: List[str] = []
    gate_report = gate_report or {}
    assets = gate_report.get("assets_detected") or {}
    has_test_doc = bool(assets.get("word_pdf")) or bool(assets.get("executable"))
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short not in _EXECUTION_SHORT:
            continue
        auth = str(row.get("achievement_authority") or "").upper()
        if "RUNTIME" not in auth and auth != "RUNTIME_VALIDATION":
            continue
        gate_row = _gate_row_for_level(gate_report, str(row.get("criteria_level") or ""))
        if _row_has_linked_evidence(row, gate_row) and has_test_doc:
            continue
        _demote_row(
            row,
            "تشغيل/كود (L4) لا يثبت تحقق معيار التنفيذ/الاختبار — مطلوب توثيق اختبار أو playtest (L5/نصي).",
        )
        row["achievement_authority"] = "RUNTIME_INSUFFICIENT"
        changes.append(f"{row.get('criteria_level')}:runtime_cap_execution")
    return changes


def apply_pro_runtime_without_academic_demotion(
    criteria_results: List[Dict[str, Any]],
    *,
    gate_report: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """M/D (and evaluative P) cannot be Achieved on runtime/L4 alone."""
    changes: List[str] = []
    gate_report = gate_report or {}
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        band = _band(str(row.get("criteria_level") or ""))
        if band not in ("M", "D"):
            continue
        auth = str(row.get("achievement_authority") or "")
        gate_row = _gate_row_for_level(gate_report, str(row.get("criteria_level") or ""))
        has_doc = bool((gate_report.get("assets_detected") or {}).get("word_pdf"))
        if auth in _RUNTIME_ONLY_AUTHORITIES and not has_doc:
            _demote_row(
                row,
                "تشغيل اللعبة/المشروع لا يثبت Merit/Distinction — مطلوب تبرير/تقييم موثّق.",
            )
            changes.append(f"{row.get('criteria_level')}:runtime_not_sufficient_academic")
        elif auth in _RUNTIME_ONLY_AUTHORITIES and not _row_has_linked_evidence(row, gate_row):
            _demote_row(
                row,
                "أدلة التشغيل (L4) دون توثيق أكاديمي مرتبط — لا يكفي لـ Merit/Distinction.",
            )
            changes.append(f"{row.get('criteria_level')}:runtime_only_merit_d")
    return changes


def apply_pro_ai_only_demotion(
    criteria_results: List[Dict[str, Any]],
    gate_report: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """Block P/M/D achieved when authority is empty/AI-only without artifact linkage."""
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        band = _band(str(row.get("criteria_level") or ""))
        if band not in ("P", "M", "D"):
            continue
        auth = str(row.get("achievement_authority") or "").upper()
        if auth and auth not in _AI_ASSERTION_ONLY:
            continue
        gate_row = _gate_row_for_level(gate_report or {}, str(row.get("criteria_level") or ""))
        if _row_has_linked_evidence(row, gate_row):
            continue
        _demote_row(
            row,
            "لا يُمنح معيار P/M/D اعتماداً على قرار الذكاء الاصطناعي فقط — "
            "مطلوب دليل مرفق مرتبط بالمعيار.",
        )
        row["achievement_authority"] = "EVIDENCE_REQUIRED"
        changes.append(f"{row.get('criteria_level')}:ai_only_blocked")
    return changes


def _teacher_feedback_excerpt(feedback: Any, limit: int = 400) -> str:
    from app.btec_criteria_governance import teacher_facing_feedback

    return teacher_facing_feedback(feedback)[:limit]


def build_pearson_audit_trail(
    grading_result: Dict[str, Any],
    *,
    evidence_matrix: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    """Per-criterion IV/EV audit entries."""
    matrix_by_level: Dict[str, Dict[str, Any]] = {}
    for row in evidence_matrix or []:
        if isinstance(row, dict) and row.get("criteria_level"):
            matrix_by_level[_short_level(str(row["criteria_level"]))] = row

    trail: List[Dict[str, Any]] = []
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        short = _short_level(level)
        mx = matrix_by_level.get(short) or {}
        achieved = bool(cr.get("achieved"))
        trail.append(
            {
                "criteria_level": level,
                "achieved": achieved,
                "awardable": cr.get("awardable"),
                "score": cr.get("score"),
                "evidence_weighted_score": cr.get("evidence_weighted_score"),
                "evidence_weight": cr.get("evidence_weight"),
                "evidence_locator_count": len(cr.get("evidence_locator") or []),
                "achievement_authority": cr.get("achievement_authority"),
                "required_artifacts": mx.get("required_artifact_keys") or [],
                "missing_artifacts": mx.get("missing_artifact_keys") or [],
                "accepted_evidence_ar": mx.get("accepted_evidence_types_ar") or [],
                "accept_reason_ar": (
                    cr.get("governance_adjustment_ar")
                    or (
                        "تحقق أكاديمياً بأدلة مرتبطة"
                        if achieved
                        else "لم يتحقق — أدلة ناقصة أو قرار حوكمة"
                    )
                ),
                "reject_reason_ar": (
                    None
                    if achieved
                    else (
                        cr.get("governance_adjustment_ar")
                        or cr.get("award_block_reason_ar")
                        or "لا يكفي الدليل لإثبات المعيار"
                    )
                ),
                "technical_note_ar": (
                    "تشغيل/ملفات: "
                    + (
                        "موثّق"
                        if str(cr.get("achievement_authority") or "").startswith("RUNTIME")
                        else "غير معتمد كدليل وحيد"
                    )
                ),
                "feedback_excerpt": _teacher_feedback_excerpt(cr.get("feedback")),
            }
        )
    return trail


def build_criteria_breakdown_for_ui(
    grading_result: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Per-criterion rows for batch-results UI (PRO / IV review)."""
    rows: List[Dict[str, Any]] = []
    gate = grading_result.get("runtime_evidence_gate") or {}
    gate_summary = str(gate.get("summary_ar") or "")
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        achieved = bool(cr.get("achieved"))
        awardable = cr.get("awardable")
        if awardable is None:
            awardable = achieved
        awardable = bool(awardable)
        gate_blocked = bool(cr.get("runtime_gate_block"))
        block_ar = _compact_gate_reason(cr, gate_summary=gate_summary)
        if achieved and not awardable and str(cr.get("award_block_reason") or "") == "missing_pass_criteria":
            achieved_display_ar = "جزئي — محجوب (Prerequisite)"
        elif achieved and not awardable:
            achieved_display_ar = "جزئي — محجوب"
        elif achieved:
            achieved_display_ar = "نعم"
        else:
            achieved_display_ar = "لا"
        if gate_blocked:
            awardable_display_ar = "لا — Gate"
        elif awardable:
            awardable_display_ar = "نعم"
        else:
            awardable_display_ar = "لا"
        rows.append(
            {
                "criteria_level": cr.get("criteria_level"),
                "achieved": achieved,
                "awardable": awardable,
                "achieved_display_ar": achieved_display_ar,
                "awardable_display_ar": awardable_display_ar,
                "gate_blocked": gate_blocked,
                "gate_reason_ar": block_ar,
                "score": cr.get("score"),
                "achievement_authority": cr.get("achievement_authority"),
                "evidence_weighted_score": cr.get("evidence_weighted_score"),
                "governance_ar": block_ar,
            }
        )
    return rows


def apply_pro_pearson_btec_package(
    grading_result: Dict[str, Any],
    *,
    grading_criteria: Optional[Sequence[Dict[str, Any]]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_mode: str = "deep",
) -> Dict[str, Any]:
    """
    PRO-only post-governance hardening + Pearson audit artifacts on grading_result.
    """
    from app.grading_mode_policy import is_fast_grading_mode

    if is_fast_grading_mode(grading_mode):
        return {"applied": False, "reason": "fast_mode_skipped"}

    criteria = grading_result.get("criteria_results")
    if not isinstance(criteria, list) or not criteria:
        return {"applied": False, "reason": "no_criteria"}

    working = copy.deepcopy(criteria)
    gate = grading_result.get("evidence_completeness_gate") or {}
    changes: List[str] = []
    changes.extend(apply_pro_evidence_gate_demotions(working, gate))
    changes.extend(apply_pro_execution_runtime_cap(working, gate_report=gate))
    changes.extend(
        apply_pro_runtime_without_academic_demotion(working, gate_report=gate)
    )
    changes.extend(apply_pro_ai_only_demotion(working, gate_report=gate))

    gameplay_preview = build_gameplay_validation_summary(artifact_inventory)
    try:
        from app.pro_engine_gameplay_governance import apply_pro_engine_gameplay_governance

        engine_changes, engine_assessment = apply_pro_engine_gameplay_governance(
            working,
            artifact_inventory,
            submission_paths=grading_result.get("submission_paths"),
            gameplay_checks=gameplay_preview.get("checks"),
        )
        changes.extend(engine_changes)
        grading_result["pro_engine_playtest_assessment"] = engine_assessment
    except Exception:
        engine_assessment = {}

    grading_result["criteria_results"] = working
    award = apply_btec_awardability(working)
    grading_result["btec_institutional_award"] = award
    inst_from_awardable = institutional_grade_from_awardable(working)
    grading_result["grade_level"] = inst_from_awardable
    grading_result["btec_institutional_award"]["institutional_grade"] = inst_from_awardable
    grading_result["btec_institutional_award"]["institutional_grade_from_awardable"] = (
        inst_from_awardable
    )
    if changes:
        pct = compute_criteria_score_pct(working)
        grading_result["criteria_score_pct"] = pct
        grading_result["percentage"] = pct
        grading_result["total_score"] = pct

    criteria_list = grading_result.get("criteria_results") or []
    apply_evidence_weighting_to_criteria(criteria_list, artifact_inventory)
    locators_by = build_evidence_locators_by_criterion(
        grading_result,
        artifact_inventory=artifact_inventory,
    )
    unit_award = validate_unit_award(criteria_list)
    unit_award["institutional_grade_from_awardable"] = inst_from_awardable
    unit_award["grade_derivation_ar"] = (
        "التقدير المؤسسي من awardable (منح رسمي) وليس من achieved أو تشغيل L4 وحده."
    )
    grading_result["btec_unit_award_validation"] = unit_award
    grading_result["grade_level"] = inst_from_awardable

    matrix = build_evidence_mapping_matrix(
        grading_criteria or [],
        gate_report=gate,
    )
    paths = grading_result.get("submission_paths") or []
    software = detect_jordan_approved_software(
        artifact_inventory=artifact_inventory,
        submission_paths=paths,
    )
    technical = build_technical_validation_summary(grading_result, artifact_inventory)
    academic = build_academic_validation_summary(grading_result)
    authenticity = build_authenticity_summary(grading_result)
    gameplay = build_gameplay_validation_summary(artifact_inventory)
    try:
        from app.pro_engine_gameplay_governance import build_engine_runtime_summary

        engine_runtime = build_engine_runtime_summary(
            artifact_inventory,
            submission_paths=grading_result.get("submission_paths"),
            gameplay_checks=gameplay.get("checks"),
        )
    except Exception:
        engine_runtime = {}
    trail = build_pearson_audit_trail(grading_result, evidence_matrix=matrix)

    package = {
        "version": PEARSON_PACKAGE_VERSION,
        "philosophy_ar": (
            "الهدف: إثبات أن الدليل المقدم يثبت تحقق المعيار — "
            "وليس أن الطالب رفع ملفات أو أن البرنامج يعمل فقط."
        ),
        "evidence_mapping_matrix": matrix,
        "evidence_locators_by_criterion": locators_by,
        "evidence_weight_model": dict(PRO_EVIDENCE_WEIGHTS),
        "technical_validation": technical,
        "academic_validation": academic,
        "authenticity": authenticity,
        "gameplay_validation": gameplay,
        "engine_runtime_summary": engine_runtime,
        "unit_award_validation": unit_award,
        "approved_software_detection": software,
        "audit_trail": trail,
        "hardening_changes": changes,
        "hardening_change_count": len(changes),
    }
    grading_result["pearson_btec_pro"] = package

    try:
        from app.iv_pack_generator import attach_iv_pack_to_grading_result

        attach_iv_pack_to_grading_result(
            grading_result,
            student_name=str(grading_result.get("student_name") or ""),
            submission_id=grading_result.get("submission_id"),
        )
    except Exception:
        pass

    return {"applied": True, "change_count": len(changes), "package": package}
