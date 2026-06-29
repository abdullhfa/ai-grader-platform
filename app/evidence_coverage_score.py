"""
Per-criterion evidence coverage % and missing-evidence report (PRO / IV / EQA).

Coverage measures *potential student evidence presence* — NOT academic achievement.
Student-authored text/files only; AI feedback and governance blocks are excluded.
"""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

from app.pro_evidence_signals import (
    classify_named_docs,
    path_looks_like_peer_design_doc,
    path_looks_like_testing_doc,
    text_has_comparison_evaluation,
    text_has_coverage_bug_log,
    text_has_coverage_test_plan,
    text_has_critical_evaluation,
    text_has_design_decisions,
    text_has_design_peer_evidence,
    text_has_improvement_from_testing,
    text_has_project_log,
    text_has_reflection,
    text_has_user_testing_evidence,
)
from app.runtime_evidence_package import package_event_names
from app.student_evidence_text import isolate_student_submission_text

CoverageFlags = Dict[str, bool | int]

COVERAGE_VERSION = "evidence_coverage_v2.6"
_CP6_MERIT_BLOCK_PCT = int(os.getenv("PRO_CP6_COVERAGE_MERIT_MIN", "50"))
_CP6_DEPENDENCY_THRESHOLD = int(os.getenv("PRO_CP6_DEPENDENCY_THRESHOLD", "40"))
# Filename-only partial credit: 10% of total C.P6 when slot max is 35%.
_CP6_PATH_ONLY_OF_MAX = 10

# Weighted C.P6 model (must sum to 100). Bug Log is optional — not all Unit 8 briefs require it.
_CP6_WEIGHTS: Dict[str, Tuple[int, str]] = {
    "test_plan": (50, "خطة اختبار (Test Plan)"),
    "user_testing": (30, "اختبار مستخدم / نتائج"),
    "runtime": (20, "أدلة تشغيل (Runtime)"),
}
_CP6_OPTIONAL_BONUS: Dict[str, Tuple[int, str]] = {
    "bug_log": (10, "سجل أخطاء (Bug Log) — اختياري"),
}

_GDD_PATH_RE = re.compile(
    r"gdd|game[\s_-]*design|وثيق[ةه]\s*تصميم|تصميم\s*اللعبة",
    re.IGNORECASE,
)
_REVIEW_TABLE_RE = re.compile(
    r"متطلب|requirement|مراجعة.*فعالية|review.*effectiveness",
    re.IGNORECASE,
)


def _short(level: str) -> str:
    lv = (level or "").strip().upper()
    return lv.split(".")[-1] if "." in lv else lv


def _pct(found: int, total: int) -> int:
    if total <= 0:
        return 0
    return round(100 * found / total)


def _path_strings(inventory: Dict[str, Any], paths: Sequence[str]) -> List[str]:
    out: List[str] = list(paths or [])
    for block_key in ("documentation", "source_code", "executable_artifacts"):
        block = inventory.get(block_key) or {}
        for f in block.get("files") or []:
            if isinstance(f, dict):
                out.append(str(f.get("path") or f.get("name") or ""))
            else:
                out.append(str(f))
    for rel in inventory.get("intake_relative_paths") or []:
        out.append(str(rel))
    return [p for p in out if p]


def _resolve_student_text(
    student_text: str,
    *,
    word_only_text: Optional[str] = None,
) -> str:
    return isolate_student_submission_text(
        student_text,
        word_only_text=word_only_text,
    )


def _base_flags(
    inventory: Dict[str, Any],
    *,
    paths: Sequence[str],
    student_text: str,
) -> CoverageFlags:
    path_list = _path_strings(inventory, paths)
    joined_paths = "\n".join(path_list)
    named = classify_named_docs(path_list)
    doc = inventory.get("documentation") or {}
    exe = inventory.get("executable_artifacts") or {}
    src = inventory.get("source_code") or {}
    rt = inventory.get("runtime_observation_report") or {}
    gvi = inventory.get("gameplay_video_inference") or {}
    l5 = inventory.get("l5_human_playtest") or {}
    pkg = inventory.get("runtime_evidence_package") or {}
    rt_events = package_event_names(pkg)

    text = student_text or ""
    has_doc = bool(doc.get("files")) or int(doc.get("file_count") or 0) > 0
    runtime_pass = str(pkg.get("runtime_status") or "").upper() == "PASS" or bool(
        rt.get("runtime_verified")
    )
    runtime_launch = "launch_success" in rt_events or bool(pkg.get("launch_success"))
    runtime_movement = "movement_observed" in rt_events or "input_detected" in rt_events
    runtime_score = "score_changed" in rt_events
    runtime_game_over = "game_over_seen" in rt_events
    runtime_win = "win_screen_seen" in rt_events
    runtime_scene = "scene_transition" in rt_events or bool(pkg.get("scene_changed"))

    test_plan_path = named["has_test_plan_doc"]
    bug_log_path = named["has_bug_log_doc"]
    user_test_path = named["has_user_test_doc"]
    test_plan_text = text_has_coverage_test_plan(text)
    bug_log_text = text_has_coverage_bug_log(text)
    user_testing_text = text_has_user_testing_evidence(text)
    user_testing = user_testing_text or user_test_path
    runtime_testing = (
        runtime_pass
        or str(l5.get("status") or "").lower() in ("completed", "verified", "done")
        or int(gvi.get("frames_sampled") or 0) > 0
    )

    return {
        "gdd_doc": bool(_GDD_PATH_RE.search(joined_paths)) or bool(
            re.search(r"gdd|وثيقة تصميم|game design", text, re.I)
        ),
        "peer_design_doc": named["has_peer_design_doc"]
        or any(path_looks_like_peer_design_doc(p) for p in path_list),
        "peer_design_text": text_has_design_peer_evidence(text, min_len=120),
        "test_plan_path": test_plan_path,
        "bug_log_path": bug_log_path,
        "user_test_path": user_test_path,
        "test_plan_text": test_plan_text,
        "bug_log_text": bug_log_text,
        "user_testing_text": user_testing_text,
        "user_testing_evidence": user_testing,
        "cp6_testing_substance": test_plan_text or bug_log_text or user_testing_text,
        "runtime_testing_evidence": runtime_testing,
        "has_exe": bool(exe.get("files")) or bool(inventory.get("has_executable_artifacts")),
        "has_src": bool(src.get("files")) or bool(inventory.get("has_source_code_artifacts")),
        "runtime_verified": bool(rt.get("runtime_verified")) or runtime_pass,
        "runtime_launch_probe": runtime_launch,
        "runtime_movement_probe": runtime_movement,
        "runtime_score_probe": runtime_score,
        "runtime_game_over_probe": runtime_game_over,
        "runtime_win_probe": runtime_win,
        "runtime_scene_probe": runtime_scene,
        "playtest_l5": str(l5.get("status") or "").lower() in ("completed", "verified", "done"),
        "gameplay_video": int(gvi.get("frames_sampled") or 0) > 0,
        "has_word_pdf": has_doc,
        "review_table_text": bool(_REVIEW_TABLE_RE.search(text)),
        "improvement_from_testing": text_has_improvement_from_testing(text)
        or user_testing
        or runtime_testing,
        "improvement_justification": text_has_improvement_from_testing(text),
        "critical_evaluation": text_has_critical_evaluation(text),
        "comparison_evaluation": text_has_comparison_evaluation(text),
        "project_log": text_has_project_log(text),
        "design_decisions": text_has_design_decisions(text),
        "reflection": text_has_reflection(text),
        "student_text_len": len(text),
    }


def _score_checks(checks: Sequence[Tuple[str, bool]]) -> Tuple[int, List[str], List[str]]:
    total = len(checks)
    found_labels: List[str] = []
    missing_labels: List[str] = []
    found_n = 0
    for label, ok in checks:
        if ok:
            found_n += 1
            found_labels.append(label)
        else:
            missing_labels.append(label)
    return _pct(found_n, total), found_labels, missing_labels


def _cp6_slot_points(
    weight: int,
    *,
    path_hit: bool,
    text_hit: bool,
    label: str,
) -> Tuple[int, Optional[str], Optional[str]]:
    """Content = full slot weight; filename only = 10% absolute (when max is 35)."""
    if text_hit:
        return weight, label, None
    if path_hit:
        partial = _CP6_PATH_ONLY_OF_MAX if weight >= 35 else max(1, round(weight * _CP6_PATH_ONLY_OF_MAX / 35))
        return partial, f"{label} (اسم ملف فقط)", None
    return 0, None, label


def _score_cp6_weighted(flags: CoverageFlags) -> Tuple[int, List[str], List[str]]:
    score = 0
    found: List[str] = []
    missing: List[str] = []
    slots = (
        (
            "test_plan",
            flags["test_plan_path"],
            flags["test_plan_text"],
        ),
        (
            "user_testing",
            flags["user_test_path"],
            flags["user_testing_text"],
        ),
    )
    for key, path_hit, text_hit in slots:
        weight, label = _CP6_WEIGHTS[key]
        pts, found_label, miss_label = _cp6_slot_points(
            weight, path_hit=path_hit, text_hit=text_hit, label=label
        )
        score += pts
        if found_label:
            found.append(found_label)
        if miss_label:
            missing.append(miss_label)
    bug_pts, bug_found, _ = _cp6_slot_points(
        _CP6_OPTIONAL_BONUS["bug_log"][0],
        path_hit=bool(flags["bug_log_path"]),
        text_hit=bool(flags["bug_log_text"]),
        label=_CP6_OPTIONAL_BONUS["bug_log"][1],
    )
    if bug_pts:
        score += bug_pts
        if bug_found:
            found.append(bug_found)
    if flags["runtime_testing_evidence"]:
        score += _CP6_WEIGHTS["runtime"][0]
        found.append(_CP6_WEIGHTS["runtime"][1])
    else:
        missing.append(_CP6_WEIGHTS["runtime"][1])
    return min(100, score), found, missing


def _row(
    level: str,
    pct: int,
    found: List[str],
    missing: List[str],
    *,
    capped_by: Optional[str] = None,
) -> Dict[str, Any]:
    entry: Dict[str, Any] = {
        "criteria_level": level,
        "coverage_pct": pct,
        "evidence_found_ar": found,
        "evidence_missing_ar": missing,
        "coverage_kind": "evidence_presence",
    }
    if capped_by:
        entry["coverage_capped_by"] = capped_by
    return entry


def _apply_cp6_dependency_ceiling(
    pct: int,
    cp6_pct: int,
    *,
    criterion: str,
) -> Tuple[int, Optional[str]]:
    if cp6_pct >= _CP6_DEPENDENCY_THRESHOLD:
        return pct, None
    ceiling = _CP6_DEPENDENCY_THRESHOLD
    if pct <= ceiling:
        return pct, None
    return ceiling, f"C.P6<{_CP6_DEPENDENCY_THRESHOLD}%"


def compute_evidence_coverage_by_criterion(
    inventory: Dict[str, Any],
    *,
    student_text: str = "",
    word_only_text: Optional[str] = None,
    submission_paths: Optional[Sequence[str]] = None,
    criteria_levels: Optional[Sequence[str]] = None,
) -> List[Dict[str, Any]]:
    isolated = _resolve_student_text(student_text, word_only_text=word_only_text)
    flags = _base_flags(inventory, paths=submission_paths or [], student_text=isolated)
    levels = list(criteria_levels or []) or [
        "8/B.P3", "8/B.P4", "8/C.P5", "8/C.P6", "8/C.P7", "8/B.M2", "8/C.M3", "8/BC.D2", "8/BC.D3",
    ]

    cp6_pct, cp6_found, cp6_missing = _score_cp6_weighted(flags)

    p3_pct, p3_found, p3_missing = _score_checks(
        [
            ("وثيقة Word/PDF", flags["has_word_pdf"]),
            ("GDD / تصميم اللعبة", flags["gdd_doc"]),
            ("محتوى تصميم في النص", flags["student_text_len"] > 400),
        ]
    )
    p4_pct, p4_found, p4_missing = _score_checks(
        [
            ("ملف مراجعة تصميم / GDD", flags["peer_design_doc"] or flags["gdd_doc"]),
            ("نص مراجعة تصميم مع الآخرين", flags["peer_design_text"]),
            ("وثيقة Word/PDF", flags["has_word_pdf"]),
        ]
    )
    p5_pct, p5_found, p5_missing = _score_checks(
        [
            ("كود مصدري / مشروع", flags["has_src"]),
            ("ملف تنفيذي", flags["has_exe"]),
            ("تشغيل مُتحقق (L4+)", flags["runtime_verified"] or flags["runtime_launch_probe"]),
            ("حركة/إدخال (Runtime)", flags["runtime_movement_probe"]),
        ]
    )
    p7_raw, p7_found, p7_missing = _score_checks(
        [
            ("جدول/نص مراجعة المتطلبات", flags["review_table_text"]),
            (
                "ربط بنتائج اختبار (P6)",
                flags["cp6_testing_substance"],
            ),
            (
                "ربط باللعبة/التنفيذ",
                flags["has_exe"]
                or flags["runtime_verified"]
                or flags["runtime_win_probe"]
                or flags["runtime_scene_probe"],
            ),
        ]
    )
    p7_pct, p7_cap = _apply_cp6_dependency_ceiling(p7_raw, cp6_pct, criterion="P7")

    m2_pct, m2_found, m2_missing = _score_checks(
        [
            ("تحليل مبرر في النص", flags["student_text_len"] > 500 and flags["design_decisions"]),
            ("أدلة تصميم", flags["gdd_doc"] or flags["peer_design_doc"]),
            ("وثائق داعمة", flags["has_word_pdf"]),
        ]
    )
    m3_raw, m3_found, m3_missing = _score_checks(
        [
            (
                "أدلة اختبار موثقة",
                flags["cp6_testing_substance"],
            ),
            ("تحسين مبني على اختبار", flags["improvement_from_testing"]),
            ("تبرير التحسين", flags["improvement_justification"]),
        ]
    )
    m3_pct, m3_cap = _apply_cp6_dependency_ceiling(m3_raw, cp6_pct, criterion="M3")

    d2_raw, d2_found, d2_missing = _score_checks(
        [
            ("تقييم نقدي", flags["critical_evaluation"]),
            ("نقاط قوة وضعف", bool(re.search(r"نقاط\s*القوة|نقاط\s*ضعف|strengths|weaknesses", isolated, re.I))),
            ("مقارنة تقنيات/عمليات", flags["comparison_evaluation"]),
        ]
    )
    d2_pct, d2_cap = _apply_cp6_dependency_ceiling(d2_raw, cp6_pct, criterion="D2")

    d3_pct, d3_found, d3_missing = _score_checks(
        [
            ("سجل تطوير/يوميات", flags["project_log"]),
            ("قرارات تصميم موثقة", flags["design_decisions"]),
            ("انعكاس شخصي", flags["reflection"]),
        ]
    )

    by_short: Dict[str, Dict[str, Any]] = {
        "P3": _row("8/B.P3", p3_pct, p3_found, p3_missing),
        "P4": _row("8/B.P4", p4_pct, p4_found, p4_missing),
        "P5": _row("8/C.P5", p5_pct, p5_found, p5_missing),
        "P6": _row("8/C.P6", cp6_pct, cp6_found, cp6_missing),
        "P7": _row("8/C.P7", p7_pct, p7_found, p7_missing, capped_by=p7_cap),
        "M2": _row("8/B.M2", m2_pct, m2_found, m2_missing),
        "M3": _row("8/C.M3", m3_pct, m3_found, m3_missing, capped_by=m3_cap),
        "D2": _row("8/BC.D2", d2_pct, d2_found, d2_missing, capped_by=d2_cap),
        "D3": _row("8/BC.D3", d3_pct, d3_found, d3_missing),
    }

    out: List[Dict[str, Any]] = []
    for lvl in levels:
        s = _short(lvl)
        if s in by_short:
            entry = dict(by_short[s])
            entry["criteria_level"] = lvl
            out.append(entry)
    return out


def build_missing_evidence_report(
    coverage_rows: Sequence[Dict[str, Any]],
    *,
    grade_level: str = "U",
    criteria_results: Optional[Sequence[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """Human-readable checklist before/after grade — IV-friendly."""
    catalog = [
        ("test_plan", "خطة اختبار (Test Plan)", lambda r: _short(r.get("criteria_level", "")) == "P6"),
        ("gameplay", "أدلة تشغيل/Gameplay", lambda r: _short(r.get("criteria_level", "")) in ("P5", "P6")),
        ("peer_review", "مراجعة التصميم مع المراجعين", lambda r: _short(r.get("criteria_level", "")) == "P4"),
        ("gdd", "وثيقة تصميم اللعبة (GDD)", lambda r: _short(r.get("criteria_level", "")) == "P3"),
    ]

    def _covered(key_sub: str) -> bool:
        for row in coverage_rows:
            found = " ".join(row.get("evidence_found_ar") or [])
            if key_sub == "test_plan" and ("خطة اختبار" in found or "Test Plan" in found):
                return True
            if key_sub == "gameplay" and ("تشغيل" in found or "Runtime" in found):
                return True
            if key_sub == "peer_review" and "مراجعة تصميم" in found:
                return True
            if key_sub == "gdd" and "GDD" in found:
                return True
        return False

    items = [
        {
            "key": key,
            "label_ar": label,
            "present": _covered(key),
            "symbol": "✓" if _covered(key) else "✗",
        }
        for key, label, _ in catalog
    ]
    missing = [i["label_ar"] for i in items if not i["present"]]
    present = [i["label_ar"] for i in items if i["present"]]

    cp6_pct = 0
    for row in coverage_rows:
        if _short(str(row.get("criteria_level") or "")) == "P6":
            cp6_pct = int(row.get("coverage_pct") or 0)
            break

    blocks_md = cp6_pct < _CP6_MERIT_BLOCK_PCT
    expected = (grade_level or "U").strip().upper() or "U"
    if blocks_md and expected in ("M", "D", "P"):
        expected = "U"

    summary_parts = []
    if missing:
        summary_parts.append("لم يتم العثور على: " + "، ".join(missing))
    if present:
        summary_parts.append("متوفر: " + "، ".join(present))
    summary_parts.append(f"تغطية C.P6: {cp6_pct}%")
    if blocks_md:
        summary_parts.append(
            f"تغطية C.P6 أقل من {_CP6_MERIT_BLOCK_PCT}% — لا يُنصح بمنح Merit/Distinction تلقائياً."
        )

    return {
        "version": COVERAGE_VERSION,
        "items": items,
        "missing_ar": missing,
        "present_ar": present,
        "cp6_coverage_pct": cp6_pct,
        "blocks_merit_distinction": blocks_md,
        "expected_grade_hint": expected,
        "expected_grade_label_ar": f"التقدير المتوقع حالياً: {expected}",
        "summary_ar": " — ".join(summary_parts),
        "coverage_note_ar": (
            "نسب التغطية تقيس وجود أدلة محتملة من ملفات الطالب فقط — "
            "ولا تعني تحقق المعيار أكاديمياً."
        ),
    }


def apply_coverage_award_governance(
    criteria_results: List[Dict[str, Any]],
    report: Dict[str, Any],
) -> List[str]:
    """Block M/D awardable when C.P6 evidence coverage is below threshold."""
    if not report.get("blocks_merit_distinction"):
        return []
    changes: List[str] = []
    for row in criteria_results:
        if not isinstance(row, dict):
            continue
        s = _short(str(row.get("criteria_level") or ""))
        if s not in ("M2", "M3", "D2", "D3"):
            continue
        if row.get("awardable") is False:
            continue
        row["awardable"] = False
        row["award_block_reason"] = "insufficient_cp6_evidence_coverage"
        row["award_block_reason_ar"] = (
            f"تغطية أدلة C.P6 ({report.get('cp6_coverage_pct', 0)}%) "
            f"أقل من {_CP6_MERIT_BLOCK_PCT}% — لا منح Merit/Distinction تلقائياً."
        )
        changes.append(f"{row.get('criteria_level')}:coverage_cp6_block")
    return changes


def attach_evidence_coverage_package(
    grading_result: Dict[str, Any],
    *,
    artifact_inventory: Optional[Dict[str, Any]] = None,
    student_text: str = "",
    word_only_text: Optional[str] = None,
    submission_paths: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    inv = artifact_inventory or grading_result.get("artifact_inventory") or {}
    levels = [
        str(r.get("criteria_level"))
        for r in grading_result.get("criteria_results") or []
        if isinstance(r, dict) and r.get("criteria_level")
    ]
    coverage = compute_evidence_coverage_by_criterion(
        inv,
        student_text=student_text,
        word_only_text=word_only_text,
        submission_paths=submission_paths,
        criteria_levels=levels or None,
    )
    report = build_missing_evidence_report(
        coverage,
        grade_level=str(grading_result.get("grade_level") or "U"),
        criteria_results=grading_result.get("criteria_results"),
    )
    changes = apply_coverage_award_governance(
        grading_result.get("criteria_results") or [], report
    )
    grading_result["evidence_coverage_by_criterion"] = coverage
    grading_result["missing_evidence_report"] = report
    grading_result["evidence_coverage_version"] = COVERAGE_VERSION
    if changes:
        grading_result.setdefault("evidence_coverage_governance", {})["changes"] = changes
    inv_out = grading_result.setdefault("artifact_inventory", inv)
    inv_out["evidence_coverage_by_criterion"] = coverage
    inv_out["missing_evidence_report"] = report
    inv_out["evidence_coverage_version"] = COVERAGE_VERSION
    return {"coverage": coverage, "report": report, "changes": changes}
