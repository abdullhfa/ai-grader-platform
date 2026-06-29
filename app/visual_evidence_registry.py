"""
Visual Evidence Registry — separates Found / Submitted / Analyzed / Used for audit-grade transparency.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Sequence

# Criteria that require PRO (runtime/game verification) in BASIC mode.
GAME_RUNTIME_PRO_SHORT_LEVELS = frozenset({"P5", "P6", "P7"})
GAME_CRITERIA_PRO_REASON_AR = "يتطلب خطة برو — المعيار يعتمد على تشغيل/تحقق اللعبة"

# Criteria that may Pass from Word/code text alone (no Vision required).
TEXT_SUFFICIENT_LEVELS = frozenset(
    {
        "P4",
        "B.P4",
        "C.P4",
        "M2",
        "B.M2",
        "C.M2",
        "M3",
        "C.M3",
        "D2",
        "BC.D2",
        "C.D2",
        "D3",
        "BC.D3",
        "C.D3",
    }
)

# Criteria that require Vision analysis and/or runtime verification for a confident Pass.
VISUAL_DEPENDENT_LEVELS = frozenset(
    {
        "P5",
        "C.P5",
        "P6",
        "C.P6",
        "P7",
        "C.P7",
    }
)

# Structured testing signals — not bare mentions of "test/اختبار".
TESTING_AUTHORITY_RULE_KEYS = frozenset(
    {
        "test_plan",
        "test_case",
        "bug_log",
        "خطة_اختبار",
        "مرحلة_الاختبار",
        "اختبار_وظيف",
        "functional_test",
        "testing_phase",
        "test_results",
        "bug_report",
    }
)

# User-testing evidence (forms/playtest) — only when snippet confirms game testing context.
_USER_TESTING_RULE_KEYS = frozenset(
    {
        "questionnaire",
        "survey",
        "استبيان",
        "استطلاع",
        "user_testing",
        "playtest",
    }
)

_USER_TESTING_SNIPPET = re.compile(
    r"(اختبار\s+اللعبة|اختبار\s+حركة|functional\s+test|playtest|user\s+test|test\s+game|"
    r"اختبار\s+وظيف|جمع\s+ملاحظات\s+المستخدم)",
    re.I,
)

_UI_DESIGN_HINTS = re.compile(
    r"\b(ui|ux|interface|hud|menu|gameplay|interactive|واجهة|تفاعل|لعبة\s+تعمل|gameplay)\b",
    re.I,
)


def _normalize_criterion_level(level: str) -> str:
    s = (level or "").strip().upper()
    return s.split(".")[-1] if "." in s else s


def is_game_runtime_pro_criterion(criteria_level: str) -> bool:
    """C.P5 / C.P6 / C.P7 — require PRO runtime verification in BASIC mode."""
    return _normalize_criterion_level(criteria_level) in GAME_RUNTIME_PRO_SHORT_LEVELS


def criterion_evidence_class(criteria_level: str, criteria_description: str = "") -> str:
    """
    text_sufficient | visual_dependent | hybrid
    hybrid = primarily text (e.g. B.P3 GDD) but may benefit from optional screenshots.
    """
    short = _normalize_criterion_level(criteria_level)
    full = (criteria_level or "").upper()
    desc = (criteria_description or "").lower()

    if short in VISUAL_DEPENDENT_LEVELS or full.endswith((".P5", ".P6", ".P7")):
        return "visual_dependent"
    if short in TEXT_SUFFICIENT_LEVELS or full.endswith((".P4", ".M2", ".M3", ".D2", ".D3")):
        return "text_sufficient"
    if _UI_DESIGN_HINTS.search(desc) or short in ("P3", "B.P3", "C.P3"):
        return "hybrid"
    return "text_sufficient"


def _vision_status(
    images_found: int,
    images_analyzed: int,
    *,
    vision_attempted: bool = False,
    vision_error: Optional[str] = None,
) -> str:
    if images_found <= 0:
        return "not_found"
    if vision_attempted and images_analyzed <= 0:
        return "failed"
    if not vision_attempted and images_analyzed <= 0:
        return "not_analysed"
    if images_analyzed >= images_found:
        return "analysed"
    return "partially_analysed"


def _vision_status_ar(
    status: str,
    *,
    images_found: int,
    images_submitted: int,
    images_analyzed: int,
    vision_error: str,
) -> str:
    if status == "not_found":
        return "لا توجد صور مضمّنة"
    if status == "failed":
        err = vision_error or "empty_vision_response"
        if images_submitted > 0:
            return f"⚠ فشل Vision — أُرسل {images_submitted} ولم يُرجَع تحليل ({err})"
        return f"⚠ فشل Vision ({err})"
    if status == "not_analysed":
        return "⚠ وُجدت صور — لم تحلل"
    if status == "partially_analysed":
        return f"حلل {images_analyzed} من {images_found}"
    return f"حلل {images_analyzed} صورة"


def build_visual_evidence_summary(
    *,
    images_found: int = 0,
    images_submitted: int = 0,
    images_analyzed: int = 0,
    video_keyframes_found: int = 0,
    video_keyframes_analyzed: int = 0,
    vision_attempted: bool = False,
    vision_completed: bool = False,
    runtime_verified: bool = False,
    vision_error: Optional[str] = None,
    vision_batches: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Submission-level visual evidence ledger."""
    images_found = max(0, images_found)
    images_submitted = max(0, images_submitted)
    images_analyzed = max(0, images_analyzed)
    video_kf_analyzed = max(0, video_keyframes_analyzed)
    video_kf_found = max(0, video_keyframes_found)
    err = (vision_error or "").strip()

    # Used = vision text merged into grading authority (completed + at least one analyzed image).
    images_used = images_analyzed if vision_completed and images_analyzed > 0 else 0
    video_used = video_kf_analyzed if vision_completed and video_kf_analyzed > 0 else 0

    status = _vision_status(
        images_found,
        images_analyzed,
        vision_attempted=vision_attempted,
        vision_error=err or None,
    )
    status_ar = _vision_status_ar(
        status,
        images_found=images_found,
        images_submitted=images_submitted,
        images_analyzed=images_analyzed,
        vision_error=err,
    )
    if video_kf_analyzed > 0 and video_kf_found > 0:
        vk_line = f"إطارات فيديو: {video_kf_analyzed} من {video_kf_found} فيديو"
        status_ar = f"{status_ar} · {vk_line}" if status_ar else vk_line

    return {
        "version": 2,
        "images_found": images_found,
        "images_submitted": images_submitted,
        "images_analyzed": images_analyzed,
        "images_used_in_decision": images_used,
        "video_keyframes_found": video_kf_found,
        "video_keyframes_analyzed": video_kf_analyzed,
        "video_keyframes_used_in_decision": video_used,
        "runtime_verified": runtime_verified,
        "vision_attempted": vision_attempted,
        "vision_completed": vision_completed,
        "vision_status": status,
        "vision_status_ar": status_ar,
        "vision_error": err,
        "vision_batches": list(vision_batches or []),
        "display_ar": (
            f"موجود: {images_found} · مرسل: {images_submitted} · "
            f"محلل: {images_analyzed}"
            + (f" | إطارات فيديو: {video_kf_analyzed}/{video_kf_found}" if video_kf_found else "")
        ),
        "disclaimer_ar": (
            "موجود = وُجد في التسليم | مرسل = أُرسل للتحليل البصري | "
            "محلل = رجع له نص تحليل | مستخدم = دخل قرار التصحيح"
        ),
    }


def fresh_vision_status_ar(ves: Dict[str, Any]) -> str:
    """Recompute Arabic vision status (never use stale snapshot vision_status_ar)."""
    if not isinstance(ves, dict):
        return ""
    summary = build_visual_evidence_summary(
        images_found=int(ves.get("images_found") or 0),
        images_submitted=int(ves.get("images_submitted") or 0),
        images_analyzed=int(ves.get("images_analyzed") or 0),
        video_keyframes_found=int(ves.get("video_keyframes_found") or 0),
        video_keyframes_analyzed=int(ves.get("video_keyframes_analyzed") or 0),
        vision_attempted=bool(ves.get("vision_attempted")),
        vision_completed=bool(ves.get("vision_completed")),
        runtime_verified=bool(ves.get("runtime_verified")),
        vision_error=ves.get("vision_error"),
    )
    return str(summary.get("vision_status_ar") or "")


def _short_level(criteria_level: str) -> str:
    return _normalize_criterion_level(criteria_level)


def _authority_requirements(criteria_level: str, evidence_class: str) -> Dict[str, bool]:
    """Which authority types this criterion needs for a confident autonomous Pass."""
    short = _short_level(criteria_level)
    if short == "P5":
        return {
            "text_authority_required": False,
            "visual_authority_required": True,
            "runtime_authority_required": True,
            "testing_authority_required": False,
            "visual_authority_optional": False,
        }
    if short == "P6":
        return {
            "text_authority_required": False,
            "visual_authority_required": False,
            "runtime_authority_required": False,
            "testing_authority_required": True,
            "visual_authority_optional": True,
        }
    if short == "P7":
        return {
            "text_authority_required": True,
            "visual_authority_required": False,
            "runtime_authority_required": True,
            "testing_authority_required": False,
            "visual_authority_optional": True,
        }
    if evidence_class == "hybrid":
        return {
            "text_authority_required": True,
            "visual_authority_required": False,
            "runtime_authority_required": False,
            "testing_authority_required": False,
            "visual_authority_optional": True,
        }
    return {
        "text_authority_required": True,
        "visual_authority_required": False,
        "runtime_authority_required": False,
        "testing_authority_required": False,
        "visual_authority_optional": False,
    }


def _testing_authority_available(
    inventory: Optional[Dict[str, Any]],
    *,
    evidence_registry: Optional[Dict[str, Any]] = None,
    criteria_level: str = "",
) -> bool:
    inv = inventory or {}
    testing = inv.get("testing_evidence") or {}
    status = str(testing.get("status") or "")
    if status in ("partial", "detected", "analyzed", "documented"):
        return True

    short = _short_level(criteria_level)
    if short != "P6":
        return False

    reg = evidence_registry or {}
    found = reg.get("evidence_found") or []
    if not isinstance(found, list):
        return False
    for item in found:
        if not isinstance(item, dict):
            continue
        key = str(item.get("rule_key") or "")
        if key in TESTING_AUTHORITY_RULE_KEYS:
            return True
        if key in _USER_TESTING_RULE_KEYS:
            blob = " ".join(
                str(item.get(k) or "")
                for k in ("snippet", "match", "rule_key")
            )
            if _USER_TESTING_SNIPPET.search(blob):
                return True
    return False


def get_criterion_authority(
    inventory: Optional[Dict[str, Any]],
    short_level: str,
) -> Dict[str, Any]:
    """Lookup per-criterion authority row — canonical source for diagnostics."""
    target = (short_level or "").strip().upper()
    if target.startswith("C."):
        target = target.split(".", 1)[-1]
    for row in (inventory or {}).get("criterion_authority") or []:
        if not isinstance(row, dict):
            continue
        if _short_level(str(row.get("criterion") or "")) == target:
            return row
    return {}


def authority_testing_available(inventory: Optional[Dict[str, Any]]) -> bool:
    """C.P6 testing authority — sole source for missing-evidence diagnostics."""
    return bool(get_criterion_authority(inventory, "P6").get("testing_authority_available"))


def authority_runtime_available(inventory: Optional[Dict[str, Any]]) -> bool:
    """C.P5 runtime authority."""
    return bool(get_criterion_authority(inventory, "P5").get("runtime_authority_available"))


def submission_testing_evidence_present(
    inventory: Optional[Dict[str, Any]],
    *,
    criteria_results: Optional[List[Dict[str, Any]]] = None,
) -> bool:
    """Legacy fallback when criterion_authority ledger is absent (old snapshots)."""
    inv = inventory or {}
    if inv.get("criterion_authority"):
        return authority_testing_available(inv)
    for cr in criteria_results or []:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        if _short_level(level) != "P6":
            continue
        reg = cr.get("evidence_registry") if isinstance(cr.get("evidence_registry"), dict) else {}
        if _testing_authority_available(
            inv,
            evidence_registry=reg,
            criteria_level=level,
        ):
            return True
    testing = inv.get("testing_evidence") or {}
    return str(testing.get("status") or "") in (
        "partial",
        "detected",
        "analyzed",
        "documented",
    )


def _text_authority_available(
    *,
    evidence_registry: Optional[Dict[str, Any]],
    achieved: bool,
    evidence_class: str,
) -> bool:
    reg = evidence_registry or {}
    found = reg.get("evidence_found") or []
    if isinstance(found, list) and len(found) > 0:
        return True
    return achieved and evidence_class in ("text_sufficient", "hybrid")


def _resolve_criterion_result(
    *,
    achieved: bool,
    verdict_status: str,
) -> tuple[str, str]:
    vs = (verdict_status or "").strip().lower()
    if vs == "inconclusive":
        return "INCONCLUSIVE", "غير حاسم — سلطة الأدلة غير كافية"
    if achieved:
        return "PASS", "متحقق"
    return "FAIL", "غير متحقق"


def build_criterion_authority_record(
    *,
    criteria_level: str,
    criteria_description: str,
    summary: Dict[str, Any],
    achieved: bool,
    verdict_status: str,
    evidence_registry: Optional[Dict[str, Any]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    decision_basis: str = "none",
    decision_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Per-criterion authority ledger — explains WHY pass/fail/inconclusive."""
    profile = criterion_evidence_class(criteria_level, criteria_description)
    req = _authority_requirements(criteria_level, profile)

    images_used = int(summary.get("images_used_in_decision") or 0)
    vision_ok = bool(summary.get("vision_completed")) and images_used > 0
    runtime_ok = bool(summary.get("runtime_verified"))
    text_ok = _text_authority_available(
        evidence_registry=evidence_registry,
        achieved=achieved,
        evidence_class=profile,
    )
    testing_ok = _testing_authority_available(
        artifact_inventory,
        evidence_registry=evidence_registry,
        criteria_level=criteria_level,
    )

    avail = {
        "text": text_ok,
        "visual": vision_ok,
        "runtime": runtime_ok,
        "testing": testing_ok,
    }

    checks: List[bool] = []
    if req["text_authority_required"]:
        checks.append(avail["text"])
    if req["visual_authority_required"]:
        checks.append(avail["visual"])
    if req["runtime_authority_required"]:
        checks.append(avail["runtime"])
    if req["testing_authority_required"]:
        checks.append(avail["testing"])
    authority_sufficient = all(checks) if checks else True

    result, result_ar = _resolve_criterion_result(
        achieved=achieved,
        verdict_status=verdict_status,
    )
    if result == "INCONCLUSIVE" and not authority_sufficient:
        if req["runtime_authority_required"] and not avail["runtime"]:
            result_ar = "غير حاسم — لا سلطة تشغيل (runtime)"
        elif req["testing_authority_required"] and not avail["testing"]:
            result_ar = "غير حاسم — لا سلطة اختبار كافية"
        elif req["visual_authority_required"] and not avail["visual"]:
            result_ar = "غير حاسم — سلطة بصرية غير متوفرة"
        else:
            result_ar = "غير حاسم — سلطة الأدلة غير كافية"
    elif result == "INCONCLUSIVE" and authority_sufficient:
        result_ar = "غير حاسم — سلطة الأدلة متوفرة؛ التقييم يتطلب مراجعة أو PRO"

    from app.rule_bundle import copy_provenance

    prov = copy_provenance(decision_provenance)

    record: Dict[str, Any] = {
        "version": 1,
        "criterion": criteria_level,
        "authority_profile": profile,
        "text_authority_required": req["text_authority_required"],
        "visual_authority_required": req["visual_authority_required"],
        "runtime_authority_required": req["runtime_authority_required"],
        "testing_authority_required": req["testing_authority_required"],
        "visual_authority_optional": req["visual_authority_optional"],
        "text_authority_available": avail["text"],
        "visual_authority_available": avail["visual"],
        "runtime_authority_available": avail["runtime"],
        "testing_authority_available": avail["testing"],
        "authority_sufficient": authority_sufficient,
        "decision_basis": decision_basis,
        "result": result,
        "result_ar": result_ar,
        "display_ar": (
            f"{criteria_level}: {result} — "
            f"text={'✓' if avail['text'] else '✗'}"
            f" visual={'✓' if avail['visual'] else '✗'}"
            f" runtime={'✓' if avail['runtime'] else '✗'}"
            f" testing={'✓' if avail['testing'] else '✗'}"
        ),
    }
    if prov:
        record["decision_provenance"] = prov
    return record


_DECISION_BASIS_AR = {
    "inconclusive_no_visual_authority": "غير حاسم — سلطة بصرية غير متوفرة",
    "inconclusive_no_runtime": "غير حاسم — لا سلطة تشغيل (runtime)",
    "inconclusive_no_testing": "غير حاسم — لا سلطة اختبار كافية",
    "inconclusive_no_structured_test_plan": "غير حاسم — لا خطة/سجل اختبار رسمي (Test Plan / Bug Log)",
    "inconclusive_formal_testing_docs_required": "غير حاسم — وثائق اختبار رسمية مطلوبة للـ Pass",
    "inconclusive_ai_guardrail": "غير حاسم — المقيّم/الحوكمة تمنع Pass رغم توفر السلطة",
    "inconclusive_insufficient_authority": "غير حاسم — سلطة الأدلة غير كافية",
}


def _resolve_inconclusive_decision_basis(
    *,
    criteria_level: str,
    evidence_class: str,
    authority_record: Dict[str, Any],
    artifact_inventory: Optional[Dict[str, Any]] = None,
    achievement_authority: str = "",
) -> str:
    """Map inconclusive verdict to the primary missing authority — not a generic visual label."""
    if evidence_class != "visual_dependent":
        return "inconclusive_insufficient_authority"
    if authority_record.get("visual_authority_required") and not authority_record.get(
        "visual_authority_available"
    ):
        return "inconclusive_no_visual_authority"
    short = _short_level(criteria_level)
    if short == "P5" and authority_record.get("runtime_authority_required") and not authority_record.get(
        "runtime_authority_available"
    ):
        return "inconclusive_no_runtime"
    if short == "P7" and authority_record.get("runtime_authority_required") and not authority_record.get(
        "runtime_authority_available"
    ):
        return "inconclusive_no_runtime"
    if short == "P6" and authority_record.get("testing_authority_required") and not authority_record.get(
        "testing_authority_available"
    ):
        return "inconclusive_no_testing"
    if authority_record.get("authority_sufficient"):
        if short == "P6":
            inv = artifact_inventory or {}
            testing = inv.get("testing_evidence") or {}
            has_formal = str(testing.get("status") or "") in (
                "partial",
                "detected",
                "analyzed",
                "documented",
            )
            if not has_formal:
                return "inconclusive_no_structured_test_plan"
            auth_tag = (achievement_authority or "").upper()
            if "INCONCLUSIVE" in auth_tag or "GUARDRAIL" in auth_tag or "REVIEW" in auth_tag:
                return "inconclusive_ai_guardrail"
            return "inconclusive_formal_testing_docs_required"
        return "inconclusive_ai_guardrail"
    return "inconclusive_insufficient_authority"


def build_criterion_visual_evidence(
    *,
    criteria_level: str,
    criteria_description: str,
    summary: Dict[str, Any],
    achieved: bool,
    verdict_status: str,
    authority: str,
    evidence_registry: Optional[Dict[str, Any]] = None,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    decision_provenance: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    ev_class = criterion_evidence_class(criteria_level, criteria_description)
    images_found = int(summary.get("images_found") or 0)
    images_analyzed = int(summary.get("images_analyzed") or 0)
    runtime_ok = bool(summary.get("runtime_verified"))

    decision_basis = "none"
    images_used = 0

    if ev_class == "text_sufficient":
        if achieved:
            decision_basis = "text"
    elif ev_class == "visual_dependent":
        if achieved and runtime_ok:
            decision_basis = "runtime"
            images_used = 0
        elif achieved and images_analyzed > 0:
            decision_basis = "vision"
            images_used = min(images_analyzed, int(summary.get("images_used_in_decision") or 0))
        elif verdict_status == "inconclusive":
            decision_basis = "pending_authority_resolution"
    elif ev_class == "hybrid":
        if achieved:
            decision_basis = "text" if images_analyzed == 0 else "text_and_vision"
            if images_analyzed > 0 and summary.get("vision_completed"):
                images_used = min(images_analyzed, int(summary.get("images_used_in_decision") or 0))

    authority_record = build_criterion_authority_record(
        criteria_level=criteria_level,
        criteria_description=criteria_description,
        summary=summary,
        achieved=achieved,
        verdict_status=verdict_status,
        evidence_registry=evidence_registry,
        artifact_inventory=artifact_inventory,
        decision_basis=decision_basis,
        decision_provenance=decision_provenance,
    )

    if verdict_status == "inconclusive" and ev_class == "visual_dependent":
        decision_basis = _resolve_inconclusive_decision_basis(
            criteria_level=criteria_level,
            evidence_class=ev_class,
            authority_record=authority_record,
            artifact_inventory=artifact_inventory,
            achievement_authority=authority,
        )
        authority_record["decision_basis"] = decision_basis
        if decision_basis in _DECISION_BASIS_AR:
            authority_record["result_ar"] = _DECISION_BASIS_AR[decision_basis]

    return {
        "evidence_class": ev_class,
        "images_found": images_found,
        "images_submitted": int(summary.get("images_submitted") or 0),
        "images_analyzed": images_analyzed,
        "images_used_in_decision": images_used,
        "video_keyframes_analyzed": int(summary.get("video_keyframes_analyzed") or 0),
        "runtime_verified": runtime_ok,
        "decision_basis": decision_basis,
        "vision_status": summary.get("vision_status", "not_found"),
        "authority": authority_record,
        "visual_authority_required": authority_record["visual_authority_required"],
        "visual_authority_available": authority_record["visual_authority_available"],
        "result": authority_record["result"],
        "result_ar": authority_record["result_ar"],
    }


def attach_visual_evidence_to_grading_result(
    grading_result: Dict[str, Any],
    *,
    images_found: int = 0,
    images_submitted: int = 0,
    images_analyzed: int = 0,
    vision_attempted: bool = False,
    vision_completed: bool = False,
    vision_error: Optional[str] = None,
    vision_batches: Optional[List[Dict[str, Any]]] = None,
    video_keyframes_found: int = 0,
    video_keyframes_analyzed: int = 0,
    runtime_verified: bool = False,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    criteria_descriptions: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Attach submission + per-criterion visual evidence to grading_result."""
    from app.rule_bundle import copy_provenance, provenance_from_payload

    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    provenance = copy_provenance(provenance_from_payload(grading_result))
    grading_result["decision_provenance"] = provenance
    emb = inv.get("embedded_screenshots") or {}
    if not images_found and isinstance(emb, dict):
        images_found = int(emb.get("count") or 0)

    obs = inv.get("runtime_observation_report") or {}
    if not runtime_verified:
        runtime_verified = bool(obs.get("runtime_verified")) or bool(
            (inv.get("runtime_validation") or {}).get("functional_smoke", {}).get(
                "functional_smoke_pass"
            )
        )

    summary = build_visual_evidence_summary(
        images_found=images_found,
        images_submitted=images_submitted,
        images_analyzed=images_analyzed,
        video_keyframes_found=video_keyframes_found,
        video_keyframes_analyzed=video_keyframes_analyzed,
        vision_attempted=vision_attempted,
        vision_completed=vision_completed,
        runtime_verified=runtime_verified,
        vision_error=vision_error,
        vision_batches=vision_batches,
    )
    grading_result["visual_evidence_summary"] = summary

    desc_map = criteria_descriptions or {}
    authority_records: List[Dict[str, Any]] = []
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        desc = desc_map.get(level) or str(cr.get("criteria_description") or cr.get("criteria_name") or "")
        reg = cr.get("evidence_registry") if isinstance(cr.get("evidence_registry"), dict) else None
        vis = build_criterion_visual_evidence(
            criteria_level=level,
            criteria_description=desc,
            summary=summary,
            achieved=bool(cr.get("achieved")),
            verdict_status=str(cr.get("verdict_status") or ""),
            authority=str(cr.get("authority") or ""),
            evidence_registry=reg,
            artifact_inventory=inv,
            decision_provenance=provenance,
        )
        authority_records.append(vis.get("authority") or {})
        if isinstance(reg, dict):
            reg["visual_evidence"] = vis
        else:
            cr["visual_evidence"] = vis

    grading_result["criterion_authority"] = authority_records
    if isinstance(inv, dict):
        inv["criterion_authority"] = authority_records
        inv["decision_provenance"] = copy_provenance(provenance)
    snap_inv = grading_result.get("artifact_inventory")
    if isinstance(snap_inv, dict) and snap_inv is not inv:
        snap_inv["criterion_authority"] = authority_records
        snap_inv["visual_evidence_summary"] = summary
        snap_inv["decision_provenance"] = copy_provenance(provenance)

    agg = grading_result.get("evidence_registry")
    if isinstance(agg, dict):
        agg["visual_evidence_summary"] = summary

    gdm = grading_result.get("grade_display_metrics")
    if isinstance(gdm, dict):
        gdm["visual_evidence"] = {
            "images_found": summary["images_found"],
            "images_submitted": summary["images_submitted"],
            "images_analyzed": summary["images_analyzed"],
            "images_used_in_decision": summary["images_used_in_decision"],
            "vision_status_ar": summary["vision_status_ar"],
            "vision_error": summary.get("vision_error", ""),
        }

    return grading_result


def sync_visual_evidence_to_inventory(
    inventory: Dict[str, Any],
    summary: Optional[Dict[str, Any]],
) -> Dict[str, Any]:
    """Keep artifact_inventory aligned with visual_evidence_summary (no false vision flags)."""
    if not summary or not isinstance(summary, dict):
        return inventory

    emb = inventory.setdefault("embedded_screenshots", {})
    if isinstance(emb, dict):
        emb["count"] = int(summary.get("images_found") or 0)
        emb["vision_submitted_count"] = int(summary.get("images_submitted") or 0)
        emb["vision_analyzed_count"] = int(summary.get("images_analyzed") or 0)
        emb["images_used_in_decision"] = int(summary.get("images_used_in_decision") or 0)
        analyzed = int(summary.get("images_analyzed") or 0)
        attempted = bool(summary.get("vision_attempted"))
        completed = bool(summary.get("vision_completed"))
        if completed and analyzed > 0:
            emb["status"] = "analyzed"
        elif attempted:
            emb["status"] = "failed"
        elif int(summary.get("images_found") or 0) > 0:
            emb["status"] = "not_analysed"
        else:
            emb["status"] = "not_detected"

    inventory["vision_analysis_used"] = bool(
        summary.get("vision_completed") and int(summary.get("images_analyzed") or 0) > 0
    )
    inventory["visual_evidence_summary"] = summary
    return inventory


def _submission_runtime_verified(grading_result: Dict[str, Any]) -> bool:
    inv = grading_result.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    ves = grading_result.get("visual_evidence_summary") or inv.get("visual_evidence_summary") or {}
    return bool(
        obs.get("runtime_verified")
        or ves.get("runtime_verified")
        or inv.get("runtime_verified")
        or (inv.get("executable_artifacts") or {}).get("runtime_verified")
    )


def apply_game_criteria_pro_gate(
    grading_result: Dict[str, Any],
    *,
    grading_mode: Optional[str] = None,
) -> Dict[str, Any]:
    """
    C.P5 / C.P6 / C.P7 depend on the game — in BASIC mode without runtime verification,
    block Pass and mark inconclusive (PRO required).
    """
    from app.grading_mode_policy import is_fast_grading_mode

    mode = grading_mode or grading_result.get("grading_mode")
    if not is_fast_grading_mode(mode):
        return grading_result
    if _submission_runtime_verified(grading_result):
        return grading_result

    changes: List[Dict[str, Any]] = []
    for cr in grading_result.get("criteria_results") or []:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        if not is_game_runtime_pro_criterion(level):
            continue
        vs = str(cr.get("verdict_status") or "").strip().lower()
        short = _normalize_criterion_level(level)
        if cr.get("achieved") or vs == "pass":
            if short == "P7" and cr.get("achieved"):
                continue
            cr["ai_proposed_achieved"] = bool(cr.get("achieved"))
            cr["achieved"] = False
            cr["verdict_status"] = "inconclusive"
            cr["achievement_authority"] = "DETERMINISTIC_INCONCLUSIVE"
            cr["requires_pro"] = True
            cr["requires_pro_reason_ar"] = GAME_CRITERIA_PRO_REASON_AR
            changes.append({"criteria_level": level, "action": "pro_gate_inconclusive"})
        elif vs == "fail":
            short = _normalize_criterion_level(level)
            if short in ("P5", "P6"):
                cr["verdict_status"] = "inconclusive"
                cr["achievement_authority"] = "DETERMINISTIC_INCONCLUSIVE"
                cr["requires_pro"] = True
                cr["requires_pro_reason_ar"] = GAME_CRITERIA_PRO_REASON_AR
                cr["pro_gate_converted_from_fail"] = True
                changes.append({"criteria_level": level, "action": "pro_gate_fail_to_inconclusive"})
            else:
                cr["requires_pro"] = True
                cr["requires_pro_reason_ar"] = GAME_CRITERIA_PRO_REASON_AR
        elif vs == "inconclusive":
            cr["requires_pro"] = True
            cr["requires_pro_reason_ar"] = GAME_CRITERIA_PRO_REASON_AR

    if changes:
        from app.btec_grade_resolution import determine_grade_level

        grading_result["grade_level"] = determine_grade_level(
            grading_result.get("criteria_results") or []
        )
    grading_result["game_criteria_pro_gate"] = {
        "version": 1,
        "criteria": sorted(GAME_RUNTIME_PRO_SHORT_LEVELS),
        "applied": bool(changes),
        "changes": changes,
        "reason_ar": GAME_CRITERIA_PRO_REASON_AR,
    }
    return grading_result
