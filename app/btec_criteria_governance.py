
from __future__ import annotations

import copy
import re
from typing import Any, Dict, List, Optional

EXECUTION_SHORT_LEVELS = frozenset({"P5", "P6", "P7", "M3"})

# Pearson prerequisite chain (short level codes, unit prefix stripped).
BTEC_PREREQUISITE_CHAIN: Dict[str, List[str]] = {
    "B.M2": ["B.P3", "B.P4"],
    "C.M3": ["C.P5", "C.P6"],
    "B.D2": ["B.P3", "B.P4", "B.M2"],
    "C.D3": ["C.P5", "C.P6", "C.M3"],
    "BC.D2": ["B.P3", "B.P4", "B.M2"],
    "BC.D3": ["C.P5", "C.P6", "C.M3"],
}

_PRAISE_WHEN_LOW_GRADE = re.compile(
    r"(?:"
    r"أداء\s+ممتاز|"
    r"متميز|"
    r"مستوى\s*Distinction|"
    r"Distinction-level|"
    r"Distinction\s*level|"
    r"بشكل\s+ممتاز"
    r")",
    re.IGNORECASE,
)

# Strong «not achieved» signals in Arabic/English feedback (achieved=True is invalid).
_SEALED_DETERMINISTIC_AUTHORITIES = frozenset(
    {
        "DESIGN_EVIDENCE_RULE_V1",
        "VISUAL_DESIGN_RULE_V1",
        "RUNTIME_VALIDATION",
        "RUNTIME_L4_GATE",
    }
)


_FEEDBACK_DENIES_ACHIEVEMENT = re.compile(
    r"(?:"
    r"لم\s+يقدم\s+الطالب|"
    r"لم\s+يقدم\s+أي|"
    r"لم\s+يُقدم\s+|"
    r"لم\s+يتم\s+|"
    r"لا\s+توجد\s+|"
    r"did\s+not\s+provide|"
    r"no\s+evidence\s+(?:of|that|was)|"
    r"without\s+(?:providing|any)\s+(?:evidence|proof|documentation)"
    r")",
    re.IGNORECASE,
)

# Softer denial — only flip M/D or execution criteria.
# Positive achievement claims while achieved=False (AI vs institutional gate).
_FEEDBACK_CLAIMS_ACHIEVEMENT = re.compile(
    r"(?:"
    r"حقق\s+الطالب|"
    r"تم\s+تحقيق\s+المعيار|"
    r"تحقق\s+(?:المعيار|بشكل\s+كامل)|"
    r"المعيار\s+تحقق|"
    r"بامتياز|"
    r"بشكل\s+ممتاز|"
    r"بشكل\s+كامل|"
    r"بالكامل|"
    r"fully\s+achieved|"
    r"student\s+achieved|"
    r"meets?\s+(?:all\s+)?requirements"
    r")",
    re.IGNORECASE,
)

# Explicit denial — must not trigger governance re-wrap (e.g. «لم يتم تحقيق المعيار»).
_FEEDBACK_DENIES_ACHIEVEMENT = re.compile(
    r"(?:"
    r"لم\s+(?:يتم\s+)?تحقيق|"
    r"لم\s+يتحقق|"
    r"لم\s+تُلبَّ?ى|"
    r"لم\s+تستوفِ|"
    r"لم\s+يُحقق|"
    r"غياب\s+أي\s+دليل|"
    r"did\s+not\s+(?:meet|achieve)|"
    r"not\s+achieved|"
    r"criterion\s+was\s+not\s+met"
    r")",
    re.IGNORECASE,
)

_MISSING_EVIDENCE_AR = {
    "source_code": "لا يظهر كود مصدري أو حزمة Godot قابلة للتحليل (.gd / project.godot / .pck)",
    "executable": "لا يوجد ملف تنفيذي (.exe / .apk / .pck)",
    "testing_evidence": "لا توجد أدلة اختبار (خطة اختبار / سجل أخطاء / نتائج اختبار اللعبة)",
    "gdd_document": "لا توجد وثيقة GDD (Word/PDF)",
    "peer_review_document": "لا يوجد توثيق مراجعة التصميم مع المراجعين (GDD / ملاحظات مراجعين)",
    "review_document": "لا يوجد تقرير مراجعة فعالية اللعبة",
}

_FEEDBACK_SOFT_DENIAL = re.compile(
    r"(?:"
    r"ولم\s+يقدم|"
    r"لكن(?:ه)?\s+لم\s+يقدم|"
    r"however,?\s+(?:the\s+student\s+)?did\s+not\s+provide|"
    r"only\s+(?:described|describes)\s+(?:theoretically|in\s+theory)"
    r")",
    re.IGNORECASE,
)

_GOVERNANCE_NOTE = "⚠️ [حوكمة BTEC]"

_BTEC_GOV_FEEDBACK_PREFIX = re.compile(
    r"^[ \t]*⚠️\s*\[حوكمة BTEC\][^\n]*\n?",
    re.MULTILINE,
)

_PARTIAL_AWARD_FEEDBACK_PREFIX = re.compile(
    r"^تحقق\s+أكاديمياً\s+جزئياً\s*—\s*لا\s+يُمنح\s+رسمياً\.?\s*",
    re.MULTILINE,
)

_AI_DISCLAIMER_TAG = re.compile(
    r"\[تحليل الذكاء الاصطناعي[^\]]*\]\s*",
    re.IGNORECASE,
)

AWARD_BLOCK_REASONS_AR = {
    "criterion_not_met": "لم يتحقق المعيار",
    "missing_pass_criteria": "يتطلب إتمام جميع معايير Pass أولاً",
    "missing_merit_criteria": "يتطلب إتمام جميع معايير Merit أولاً",
}


def _short_level(criteria_level: str) -> str:
    lv = (criteria_level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def _band(criteria_level: str) -> str:
    short = _short_level(criteria_level)
    if short.startswith("P"):
        return "P"
    if short.startswith("M"):
        return "M"
    if short.startswith("D"):
        return "D"
    return ""


def strip_btec_governance_feedback(text: str) -> str:
    """Remove internal BTEC governance wrappers from teacher-facing feedback."""
    if not text:
        return ""
    cleaned = text.strip()
    for _ in range(12):
        prev = cleaned
        cleaned = _BTEC_GOV_FEEDBACK_PREFIX.sub("", cleaned)
        cleaned = _PARTIAL_AWARD_FEEDBACK_PREFIX.sub("", cleaned)
        cleaned = _AI_DISCLAIMER_TAG.sub("", cleaned)
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()
        if cleaned == prev:
            break
    return cleaned


def teacher_facing_feedback(text: object) -> str:
    """Single entry point for human-visible criterion feedback."""
    return strip_btec_governance_feedback(str(text or ""))


def sanitize_all_criteria_feedback(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """Strip internal governance/AI wrappers from every criterion feedback row."""
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        raw = str(row.get("feedback") or "")
        if not raw:
            continue
        clean = teacher_facing_feedback(raw)
        if clean != raw:
            row["feedback"] = clean
            changes.append(f"{row.get('criteria_level')}:feedback_sanitized")
    return changes


def ensure_clean_grading_result_feedback(grading_result: Dict[str, Any]) -> List[str]:
    """Sanitize all criterion feedback inside a grading payload before persistence/UI."""
    return sanitize_all_criteria_feedback(grading_result.get("criteria_results") or [])


def _feedback_text(row: Dict[str, Any]) -> str:
    return str(row.get("feedback") or row.get("reasoning") or "").strip()


def _demote_row(row: Dict[str, Any], reason_ar: str) -> None:
    if not row.get("achieved"):
        return
    row["achieved"] = False
    row["verdict_status"] = "fail"
    row["score"] = min(int(row.get("score") or 0), 35)
    row["governance_adjustment_ar"] = reason_ar
    if isinstance(row.get("decision_matrix"), list) and row["decision_matrix"]:
        row["decision_matrix"][0]["met"] = False


def _has_informative_artifact_signal(
    inventory: Optional[Dict[str, Any]],
    grading_result: Optional[Dict[str, Any]],
) -> bool:
    """True if we have *any* concrete evidence stream to judge game artifacts.

    Distinguishes "inventory says no artifacts" (judge → may demote) from
    "we have no inventory/paths at all" (unknown → must not demote)."""
    if isinstance(inventory, dict) and inventory:
        return True
    gr = grading_result or {}
    for key in ("submission_paths", "intake_relative_paths"):
        if gr.get(key):
            return True
    gate = gr.get("evidence_completeness_gate")
    if isinstance(gate, dict) and gate.get("assets_detected"):
        return True
    return False


def _submission_has_game_artifacts(
    inventory: Optional[Dict[str, Any]],
    *,
    grading_result: Optional[Dict[str, Any]] = None,
) -> bool:
    if not isinstance(inventory, dict):
        inventory = {}
    try:
        from app.criteria_result_finalizer import _resolve_assets

        assets = _resolve_assets(grading_result or {}, inventory)
        if assets.get("has_exe"):
            return True
    except Exception:
        pass
    if inventory.get("has_source_code_artifacts") or inventory.get("has_executable_artifacts"):
        return True
    sc = inventory.get("source_code") or inventory.get("source_code_artifacts") or {}
    if sc.get("status") in ("analyzed", "detected") and sc.get("files"):
        return True
    for f in sc.get("files") or []:
        if isinstance(f, dict) and (
            f.get("source_kind") == "godot_pck_embedded" or (f.get("ext") or "").lower() == ".gd"
        ):
            return True
    exe = inventory.get("executable_artifacts") or {}
    if exe.get("files"):
        return True
    runtime = inventory.get("runtime_observation_report") or {}
    if runtime.get("runtime_verified"):
        return True
    rt = inventory.get("runtime_artifacts") or {}
    if (
        rt.get("gamemaker_detected")
        or rt.get("gamemaker_build_detected")
        or rt.get("scratch_detected")
        or rt.get("godot_export_detected")
        or rt.get("unity_build_detected")
        or rt.get("html5_build_detected")
    ):
        return True
    gate = (grading_result or {}).get("evidence_completeness_gate") or {}
    assets = gate.get("assets_detected") or {}
    if assets.get("executable") or assets.get("source_code"):
        return True
    # Path-based fallback: a slim/early inventory may lack runtime/source flags while
    # the submission clearly contains a game project (.sb3 Scratch, .yyp GameMaker,
    # project.godot, .uproject, …). Scanning the raw paths prevents a false
    # "no project/code/executable" demotion of P5/P6/P7/M3 for valid game uploads.
    try:
        from app.game_engine_signatures import (
            detect_engine_from_text,
            has_runnable_game_project,
        )

        path_pool: List[str] = []
        for src in (
            (grading_result or {}).get("submission_paths"),
            (grading_result or {}).get("intake_relative_paths"),
            inventory.get("submission_paths"),
        ):
            if isinstance(src, list):
                path_pool.extend(str(p) for p in src if p)
        joined = "\n".join(path_pool).lower().replace("\\", "/")
        if joined and (has_runnable_game_project(joined) or detect_engine_from_text(joined)):
            return True
    except Exception:
        pass
    return False


def _institutional_not_achieved_reason_ar(row: Dict[str, Any]) -> str:
    parts: List[str] = []
    gov = str(row.get("governance_adjustment_ar") or "").strip()
    if gov:
        parts.append(gov)
    det = row.get("deterministic_rubric") or {}
    reason = str(det.get("reason") or "").strip()
    if reason.startswith("missing_evidence:"):
        keys = [k.strip() for k in reason.split(":", 1)[-1].split(",") if k.strip()]
        for key in keys:
            parts.append(_MISSING_EVIDENCE_AR.get(key, key))
    elif reason and reason not in parts:
        parts.append(reason)
    auth = str(row.get("achievement_authority") or "")
    if auth in ("RUNTIME_INSUFFICIENT", "HUMAN_REVIEW_REQUIRED") and row.get("runtime_observation_note_ar"):
        parts.append(
            "أدلة التشغيل الآلية (L4) لا تكفي لإثبات تحقق معيار الإنتاج/الاختبار — مطلوب مراجعة بشرية (L5) أو playtest موثّق."
        )
    if not parts:
        parts.append("لم تستوفِ شروط الأدلة أو التشغيل المؤسسية لهذا المعيار.")
    return "؛ ".join(dict.fromkeys(parts))


def enforce_not_achieved_feedback_consistency(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """Align teacher-facing feedback when achieved=False but AI text claims success."""
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or row.get("achieved"):
            continue
        raw = _feedback_text(row)
        if _GOVERNANCE_NOTE in raw or "[تحليل الذكاء الاصطناعي" in raw:
            body = strip_btec_governance_feedback(raw)
            if body != raw:
                row["feedback"] = body
                changes.append(f"{row.get('criteria_level')}:feedback_sanitized")
            continue
        fb = strip_btec_governance_feedback(raw)
        if not fb or _FEEDBACK_DENIES_ACHIEVEMENT.search(fb):
            continue
        if not _FEEDBACK_CLAIMS_ACHIEVEMENT.search(fb):
            continue
        reason_ar = _institutional_not_achieved_reason_ar(row)
        row["feedback"] = f"لم يتحقق المعيار مؤسسياً. {reason_ar}"
        if isinstance(row.get("decision_matrix"), list) and row["decision_matrix"]:
            if isinstance(row["decision_matrix"][0], dict):
                row["decision_matrix"][0]["met"] = False
        changes.append(f"{row.get('criteria_level')}:not_achieved_feedback_aligned")
    return changes


_STALE_DENIAL_SENTENCES = (
    "أدلة التشغيل الآلية (L4) لا تكفي لإثبات تحقق معيار الإنتاج/الاختبار — مطلوب مراجعة بشرية (L5) أو playtest موثّق.",
    "تشغيل/كود (L4) لا يثبت تحقق معيار التنفيذ/الاختبار — مطلوب توثيق اختبار أو playtest (L5/نصي).",
)

# Plain-Arabic positive explanations for the deterministic design-evidence rules
# (app/design_evidence_assessor.py). Keyed by the reason-code prefix before "=".
_ACHIEVED_REASON_PREFIX_AR = {
    "bp3_signals": (
        "تحقق المعيار من خلال: وصف/وثيقة لتصميم اللعبة، بنية لعب واضحة "
        "(ميكانيكيات أو مستويات أو تحكم)، وعناصر تصميم بصري موثقة في تقرير الطالب."
    ),
    "bp4_visual_signals": (
        "تحقق المعيار من خلال: عناصر تصميم بصري للواجهة/الشاشات موثقة في تقرير "
        "الطالب، إلى جانب استبيان أو قسم اختبار للتصميم."
    ),
}


def _institutional_achieved_reason_ar(row: Dict[str, Any]) -> str:
    """Plain-Arabic, evidence-grounded reason an achieved=True row is achieved.

    Never invents evidence: falls back to a generic, rule-scoped statement
    when no specific signal codes are available.
    """
    det = row.get("deterministic_rubric") or {}
    reason = str(det.get("reason") or "").strip()
    prefix = reason.split("=", 1)[0]
    if prefix in _ACHIEVED_REASON_PREFIX_AR:
        return _ACHIEVED_REASON_PREFIX_AR[prefix]
    rule_id = str(row.get("rule_id") or det.get("rule_id") or "").strip()
    if rule_id == "evidence_gate":
        return (
            "تشغيل ناجح موثّق + ميكانيكيات مثبتة من كود المشروع (أدلة ملف:سطر)، "
            "أو فيديو لعب/مراجعة معلم موثّقة."
        )
    gov = str(row.get("governance_adjustment_ar") or "").strip()
    if gov:
        return gov
    return "استوفى المعيار الأدلة الأساسية المطلوبة وفق قواعد التصحيح الحتمية لهذا المعيار."


def enforce_achieved_feedback_consistency(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """
    Align teacher-facing feedback when achieved=True but the stored feedback
    text (written by the AI pass *before* a deterministic rule or the runtime
    gate later flipped the row to achieved=True) still reads as a denial —
    e.g. "لم يتم تحقيق المعيار... screenshot_count: 0". Partial/leading-sentence
    stripping is not reliable across arbitrary AI phrasing, so once ANY denial
    signal is detected anywhere in the text, the whole feedback is replaced
    with an accurate, rule-grounded positive statement. The report must never
    say a criterion was not met for a row the system has certified achieved.
    """
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue

        # Decision-matrix consistency: an achieved criterion must not display
        # "غير متحقق" for requirement rows that carry cited evidence — that met
        # flag was force-cleared by an earlier (overturned) demotion layer.
        matrix = row.get("decision_matrix")
        if isinstance(matrix, list):
            for cell in matrix:
                if not isinstance(cell, dict) or cell.get("met"):
                    continue
                evidence = str(
                    cell.get("evidence") or cell.get("evidence_ref") or ""
                ).strip()
                if evidence and evidence not in ("-", "—", "Not found"):
                    cell["met"] = True
                    changes.append(
                        f"{row.get('criteria_level')}:decision_matrix_met_aligned"
                    )

        raw = _feedback_text(row)
        if not raw:
            continue
        denies = bool(_FEEDBACK_DENIES_ACHIEVEMENT.search(raw)) or any(
            sentence in raw for sentence in _STALE_DENIAL_SENTENCES
        )
        if not denies:
            continue
        reason_ar = _institutional_achieved_reason_ar(row)
        row["feedback"] = f"تحقق المعيار. {reason_ar}"
        changes.append(f"{row.get('criteria_level')}:achieved_feedback_aligned")
    return changes


def _short_criterion_code(level: str) -> str:
    lv = str(level or "").strip()
    if "/" in lv:
        lv = lv.split("/", 1)[-1]
    return lv


def _achieved_short_levels(criteria_results: List[Dict[str, Any]]) -> Dict[str, bool]:
    out: Dict[str, bool] = {}
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        code = _short_criterion_code(str(row.get("criteria_level") or ""))
        if code:
            out[code] = bool(row.get("achieved"))
    return out


def _prerequisite_block_reason_ar(level: str, achieved_map: Dict[str, bool]) -> str:
    code = _short_criterion_code(level)
    prereqs = BTEC_PREREQUISITE_CHAIN.get(code) or []
    missing = [p for p in prereqs if not achieved_map.get(p)]
    if missing:
        joined = " و".join(missing)
        return f"يتطلب إتمام {joined} أولاً."
    return AWARD_BLOCK_REASONS_AR.get("missing_pass_criteria", "")


_PREREQ_CODE_RE = re.compile(r"\b[BC]\.[PMD]\d\b")

# Plain-Arabic explanation of *this row's own* shortfall (independent of any
# prerequisite), keyed by the deterministic rule's reason code — used once a
# stale "prerequisite not met" claim has been cleared away and needs to be
# replaced with the row's real, still-valid reason for not being achieved.
_DET_NOT_ACHIEVED_REASON_AR = {
    "merit_analysis_missing": (
        "لا يظهر في تقرير الطالب تحليل نقدي كافٍ لفعالية أو جودة تصميم اللعبة "
        "بالعمق والتفصيل المطلوبين لمستوى Merit."
    ),
    "distinction_evaluation_missing": (
        "لا يظهر في تقرير الطالب تقييم نقدي شامل (نقاط قوة وضعف وتوصيات تحسين) "
        "بالعمق والتفصيل المطلوبين لمستوى Distinction."
    ),
    "presentation_insufficient": (
        "لم يقدَّم دليل عرض تقديمي (شرائح أو تسجيل) موجّه لجمهور تقني."
    ),
}


def enforce_prerequisite_citation_consistency(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """Fix stale prerequisite citations in Merit/Distinction feedback.

    A Merit/Distinction row's feedback is often written by the AI pass in the
    same batch as — and sometimes citing — its Pass-level prerequisites
    (e.g. "لا يمكن منح Merit لأن B.P3 و B.P4 لم يتم تحقيقها"). When those
    prerequisites are later promoted to achieved=True by a deterministic rule
    or the runtime gate, that citation goes stale: the report ends up
    claiming a criterion is blocked by prerequisites the same report shows as
    achieved. This rewrites the feedback using the current, final achieved
    map — either the real (still-missing) prerequisite reason, or, if the
    prerequisites are now all satisfied, this row's own remaining shortfall.
    """
    changes: List[str] = []
    achieved_map = _achieved_short_levels(criteria_results)
    for row in criteria_results:
        if not isinstance(row, dict) or row.get("achieved"):
            continue
        level = str(row.get("criteria_level") or "")
        short = _short_criterion_code(level)
        prereqs = BTEC_PREREQUISITE_CHAIN.get(short) or []
        if not prereqs:
            continue
        fb = _feedback_text(row)
        if not fb:
            continue
        cited_codes = set(_PREREQ_CODE_RE.findall(fb))
        if not cited_codes:
            continue
        stale = any(
            code in prereqs and achieved_map.get(code) for code in cited_codes
        )
        if not stale:
            continue
        still_missing = [p for p in prereqs if not achieved_map.get(p)]
        if still_missing:
            reason_ar = _prerequisite_block_reason_ar(level, achieved_map)
        else:
            det = row.get("deterministic_rubric") or {}
            det_reason = str(det.get("reason") or "")
            own_reason_ar = _DET_NOT_ACHIEVED_REASON_AR.get(det_reason)
            prereq_list = "، ".join(prereqs)
            if own_reason_ar:
                reason_ar = f"معايير Pass/Merit المرتبطة ({prereq_list}) متحققة الآن — {own_reason_ar}"
            else:
                reason_ar = (
                    f"معايير Pass/Merit المرتبطة ({prereq_list}) متحققة الآن، لكن هذا "
                    "المعيار نفسه لم يستوفِ بعد الأدلة المطلوبة له."
                )
        row["feedback"] = f"لم يتحقق المعيار. {reason_ar}"
        changes.append(f"{level}:prerequisite_citation_aligned")
    return changes


def _teacher_block_reason_ar(reason: str) -> str:
    """Normalize internal award-block codes into plain teacher-facing Arabic."""
    r = str(reason or "").strip()
    if not r:
        return ""
    r = re.sub(r"^محجوب\s*—\s*", "", r)
    r = re.sub(r"\s*\(Prerequisite\)\s*$", "", r, flags=re.IGNORECASE)
    for old, new in (
        (
            "تحقق أكاديمياً — لا يُمنح رسمياً (معايير Pass ناقصة)",
            AWARD_BLOCK_REASONS_AR["missing_pass_criteria"],
        ),
        (
            "تحقق أكاديمياً — لا يُمنح رسمياً (معايير Merit ناقصة)",
            AWARD_BLOCK_REASONS_AR["missing_merit_criteria"],
        ),
        ("المعيار لم يتحقق أكاديمياً", AWARD_BLOCK_REASONS_AR["criterion_not_met"]),
    ):
        r = r.replace(old, new)
    if re.search(r"لم\s+ي[ُu]?تحقق", r, flags=re.IGNORECASE):
        codes = re.sub(r"\s+لم\s+ي[ُu]?تحقق.*$", "", r, flags=re.IGNORECASE).strip()
        if codes:
            return f"يتطلب إتمام {codes} أولاً."
    return r.rstrip(".")


def enforce_achieved_not_awardable_feedback(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """Clarify teacher feedback when achieved=True but awardable=False."""
    changes: List[str] = []
    achieved_map = _achieved_short_levels(criteria_results)
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        if row.get("awardable", True):
            continue
        level = str(row.get("criteria_level") or "")
        reason = _teacher_block_reason_ar(str(row.get("award_block_reason_ar") or "").strip())
        if not reason:
            reason = _prerequisite_block_reason_ar(level, achieved_map)
        if not reason:
            reason = _teacher_block_reason_ar(
                AWARD_BLOCK_REASONS_AR.get(str(row.get("award_block_reason") or ""), "")
            )
        raw = strip_btec_governance_feedback(_feedback_text(row))
        praise_only = (
            not raw
            or (len(raw) < 100 and _PRAISE_WHEN_LOW_GRADE.search(raw))
            or (len(raw) < 80 and _FEEDBACK_CLAIMS_ACHIEVEMENT.search(raw))
        )
        if praise_only:
            row["feedback"] = (
                f"تحقق المعيار جزئياً. {reason}".strip() if reason else "تحقق المعيار جزئياً."
            )
        elif reason and reason not in raw:
            row["feedback"] = f"{raw}\n\n{reason}"
        else:
            row["feedback"] = raw
        row["report_display_status"] = "partial_blocked"
        changes.append(f"{level}:achieved_not_awardable_feedback")
    return changes


def align_overall_feedback_with_institutional_grade(
    grading_result: Dict[str, Any],
) -> List[str]:
    """When institutional grade is U/R, remove Distinction praise and add honest guidance."""
    grade = str(grading_result.get("grade_level") or "").strip().upper()
    if grade not in ("U", "R", "REFERRAL"):
        return []

    fb = str(grading_result.get("overall_feedback") or "").strip()
    gate = grading_result.get("runtime_evidence_gate") or {}
    gate_blocked = isinstance(gate, dict) and gate.get("runtime_status") == "BLOCKED"
    has_praise = bool(_PRAISE_WHEN_LOW_GRADE.search(fb))
    if not has_praise and not gate_blocked:
        return []

    corrective = (
        "الطالب أنتج وثائق تصميم ومواد مشروع تدل على جهد حقيقي، "
        "لكن لم تُثبَت أدلة تشغيل الألعاب الفعلية (Gameplay) المطلوبة لتحقيق معايير التنفيذ "
        "(مثل C.P5/C.P6). للحصول على Pass أو أعلى: يُطلب فيديو gameplay موثّق، "
        "أو Runtime PASS يثبت اللعب الفعلي (L4/L5)."
    )

    gov_note = ""
    if _GOVERNANCE_NOTE in fb:
        idx = fb.index(_GOVERNANCE_NOTE)
        gov_note = fb[idx:].strip()
        fb = fb[:idx].strip()

    cleaned_lines = [
        ln for ln in fb.split("\n") if ln.strip() and not _PRAISE_WHEN_LOW_GRADE.search(ln)
    ]
    rest = "\n".join(cleaned_lines).strip()
    parts = [corrective]
    if rest:
        parts.append(rest)
    if gov_note:
        parts.append(gov_note)
    grading_result["overall_feedback"] = "\n\n".join(parts)
    return ["overall_feedback_aligned_with_grade"]


def enforce_feedback_achieved_consistency(
    criteria_results: List[Dict[str, Any]],
) -> List[str]:
    """Flip achieved when feedback explicitly states missing evidence."""
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        auth = str(row.get("achievement_authority") or "")
        det = row.get("deterministic_rubric") or {}
        if auth in _SEALED_DETERMINISTIC_AUTHORITIES and det.get("deterministic_achieved"):
            continue
        fb = _feedback_text(row)
        if not fb:
            continue
        level = str(row.get("criteria_level") or "")
        short = _short_level(level)
        band = _band(level)
        hard_deny = bool(_FEEDBACK_DENIES_ACHIEVEMENT.search(fb))
        soft_deny = bool(_FEEDBACK_SOFT_DENIAL.search(fb))
        if hard_deny:
            _demote_row(
                row,
                "الملاحظة تنفي وجود الدليل المطلوب — لا يمكن اعتبار المعيار متحققاً.",
            )
            changes.append(f"{level}:feedback_contradiction")
        elif soft_deny and (band in ("M", "D") or short in EXECUTION_SHORT_LEVELS):
            _demote_row(
                row,
                "الملاحظة تشير إلى نقص جوهري في الدليل — تم إلغاء Merit/Distinction أو معيار التنفيذ.",
            )
            changes.append(f"{level}:soft_feedback_contradiction")
    return changes


def enforce_execution_artifact_requirements(
    criteria_results: List[Dict[str, Any]],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    grading_result: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """P5/P6/P7/M3 cannot be achieved without attached game project or executable."""
    if _submission_has_game_artifacts(artifact_inventory, grading_result=grading_result):
        return []
    # Guard: only demote when we actually have an inventory to judge. A *missing*
    # inventory (e.g. early single-grade stub pass before artifacts are attached)
    # is "unknown", not "no artifacts" — demoting here wrongly stamps a false
    # "لا توجد ملفات مشروع" on valid game uploads. The later full-inventory
    # governance pass re-checks with real evidence.
    if not _has_informative_artifact_signal(artifact_inventory, grading_result):
        return []
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict) or not row.get("achieved"):
            continue
        short = _short_level(str(row.get("criteria_level") or ""))
        if short not in EXECUTION_SHORT_LEVELS:
            continue
        _demote_row(
            row,
            "معيار تنفيذ/اختبار/تحسين اللعبة — لا توجد ملفات مشروع أو كود أو ملف تشغيل مرفق.",
        )
        changes.append(f"{row.get('criteria_level')}:missing_game_artifacts")
    return changes


def compute_criteria_score_pct(criteria_results: List[Dict[str, Any]]) -> int:
    """Analytical average of per-criterion scores — independent of BTEC band."""
    total_n = len(criteria_results) or 1
    return int(
        sum(int(r.get("score") or 0) for r in criteria_results if isinstance(r, dict))
        / total_n
    )


def recalculate_institutional_grade(criteria_results: List[Dict[str, Any]]) -> str:
    """Return BTEC institutional award band (U if Pass incomplete)."""
    from app.btec_grade_resolution import determine_grade_level

    return determine_grade_level(criteria_results)


def _band_rows(criteria_results: List[Dict[str, Any]]) -> tuple[List[Dict], List[Dict], List[Dict]]:
    p_rows, m_rows, d_rows = [], [], []
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        band = _band(str(row.get("criteria_level") or ""))
        if band == "P":
            p_rows.append(row)
        elif band == "M":
            m_rows.append(row)
        elif band == "D":
            d_rows.append(row)
    return p_rows, m_rows, d_rows


def apply_btec_awardability(criteria_results: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Pearson model: keep ``achieved`` as academic evidence; set ``awardable`` separately.

    M/D may be achieved=True but awardable=False when lower bands are incomplete.
    """
    p_rows, m_rows, d_rows = _band_rows(criteria_results)
    all_p = len(p_rows) > 0 and all(r.get("achieved") for r in p_rows)
    all_m = len(m_rows) > 0 and all(r.get("achieved") for r in m_rows)

    achieved_not_awardable: List[str] = []

    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        level = str(row.get("criteria_level") or "")
        band = _band(level)
        achieved = bool(row.get("achieved"))

        if not achieved:
            row["awardable"] = False
            row["award_block_reason"] = "criterion_not_met"
            row["award_block_reason_ar"] = AWARD_BLOCK_REASONS_AR["criterion_not_met"]
            continue

        if band == "P":
            row["awardable"] = True
            row.pop("award_block_reason", None)
            row.pop("award_block_reason_ar", None)
        elif band == "M":
            if all_p:
                row["awardable"] = True
                row.pop("award_block_reason", None)
                row.pop("award_block_reason_ar", None)
            else:
                row["awardable"] = False
                row["award_block_reason"] = "missing_pass_criteria"
                row["award_block_reason_ar"] = AWARD_BLOCK_REASONS_AR["missing_pass_criteria"]
                achieved_not_awardable.append(level)
        elif band == "D":
            if all_p and all_m:
                row["awardable"] = True
                row.pop("award_block_reason", None)
                row.pop("award_block_reason_ar", None)
            elif not all_p:
                row["awardable"] = False
                row["award_block_reason"] = "missing_pass_criteria"
                row["award_block_reason_ar"] = AWARD_BLOCK_REASONS_AR["missing_pass_criteria"]
                achieved_not_awardable.append(level)
            else:
                row["awardable"] = False
                row["award_block_reason"] = "missing_merit_criteria"
                row["award_block_reason_ar"] = AWARD_BLOCK_REASONS_AR["missing_merit_criteria"]
                achieved_not_awardable.append(level)
        else:
            row["awardable"] = achieved

    missing_pass = [str(r.get("criteria_level")) for r in p_rows if not r.get("achieved")]
    missing_merit = [str(r.get("criteria_level")) for r in m_rows if not r.get("achieved")]
    missing_pass_short = [_short_criterion_code(x) for x in missing_pass if x]
    missing_pass_label = " و".join(missing_pass_short) if missing_pass_short else ""

    if missing_pass_label:
        block_ar = f"يتطلب إتمام {missing_pass_label} أولاً."
        for row in criteria_results:
            if not isinstance(row, dict):
                continue
            if (
                row.get("achieved")
                and not row.get("awardable")
                and row.get("award_block_reason") == "missing_pass_criteria"
            ):
                row["award_block_reason_ar"] = block_ar

    institutional_grade = recalculate_institutional_grade(criteria_results)

    if institutional_grade == "U" and missing_pass:
        reason_code = "missing_pass_criteria"
        reason_ar = "لم يحقق جميع معايير Pass — التقدير المؤسسي U / Referral."
    elif institutional_grade == "U":
        reason_code = "incomplete_unit"
        reason_ar = "لم يكتمل الحد الأدنى لمتطلبات الوحدة."
    elif institutional_grade == "P" and missing_merit and any(r.get("achieved") for r in m_rows + d_rows):
        reason_code = "pass_only"
        reason_ar = "Pass فقط — Merit/Distinction غير مكتملة للمنح الرسمي."
    else:
        reason_code = "band_complete"
        reason_ar = ""

    return {
        "institutional_grade": institutional_grade,
        "reason_code": reason_code,
        "reason_ar": reason_ar,
        "missing_pass_criteria": missing_pass,
        "missing_merit_criteria": missing_merit,
        "achieved_not_awardable": achieved_not_awardable,
    }


def apply_btec_criteria_governance(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Normalize criteria_results in-place; refresh grade_level and percentage.
    Returns governance report dict.
    """
    criteria = grading_result.get("criteria_results")
    if not isinstance(criteria, list) or not criteria:
        return {"applied": False, "changes": []}

    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    original_grade = str(grading_result.get("grade_level") or "")
    working = copy.deepcopy(criteria)

    # Preserve analytical score snapshot before governance row demotions.
    criteria_score_pct = (
        grading_result.get("criteria_score_pct")
        or grading_result.get("percentage")
        or compute_criteria_score_pct(working)
    )
    try:
        criteria_score_pct = int(criteria_score_pct)
    except (TypeError, ValueError):
        criteria_score_pct = compute_criteria_score_pct(working)

    all_changes: List[str] = []
    all_changes.extend(enforce_feedback_achieved_consistency(working))
    all_changes.extend(
        enforce_execution_artifact_requirements(
            working, artifact_inventory=inv, grading_result=grading_result
        )
    )

    for row in working:
        if isinstance(row, dict) and row.get("feedback") and row.get("achieved"):
            row["feedback"] = strip_btec_governance_feedback(str(row["feedback"]))

    awardability = apply_btec_awardability(working)
    new_grade = awardability["institutional_grade"]
    grading_result["btec_institutional_award"] = awardability
    all_changes.extend(enforce_not_achieved_feedback_consistency(working))
    all_changes.extend(enforce_achieved_not_awardable_feedback(working))
    all_changes.extend(sanitize_all_criteria_feedback(working))
    all_changes.extend(align_overall_feedback_with_institutional_grade(grading_result))
    grading_result["criteria_results"] = working
    grading_result["grade_level"] = new_grade
    grading_result["criteria_score_pct"] = criteria_score_pct
    grading_result["percentage"] = criteria_score_pct
    grading_result["total_score"] = criteria_score_pct
    grading_result["max_score"] = grading_result.get("max_score") or 100

    if not all_changes:
        return {
            "applied": False,
            "changes": [],
            "original_grade_level": original_grade,
            "institutional_grade_level": new_grade,
            "criteria_score_pct": criteria_score_pct,
            "awardability": awardability,
        }

    note = (
        f"\n\n{_GOVERNANCE_NOTE} تم تعديل {len(all_changes)} معيار(اً): "
        f"{original_grade} → {new_grade}. "
        f"({', '.join(all_changes[:8])}{'…' if len(all_changes) > 8 else ''})"
    )
    grading_result["overall_feedback"] = (grading_result.get("overall_feedback") or "") + note

    report = {
        "applied": True,
        "changes": all_changes,
        "change_count": len(all_changes),
        "original_grade_level": original_grade,
        "institutional_grade_level": new_grade,
        "criteria_score_pct": criteria_score_pct,
        "awardability": awardability,
        "summary_ar": (
            f"حوكمة BTEC: {len(all_changes)} تصحيح(ات) — "
            f"{original_grade} → {new_grade} "
            f"(نسبة المعايير {criteria_score_pct}%)"
        ),
    }
    grading_result["btec_criteria_governance"] = report
    return report
