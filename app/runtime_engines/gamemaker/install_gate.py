"""
GameMaker source-only install gate (no .exe).

Policy (teacher-mandated):
  1. If a runnable .exe / data.win / HTML5 entry exists → do nothing here
     (existing executable grading path stays untouched).
  2. If the submission is GameMaker source (.yyp/.gml/.yyz) and GameMaker IDE
     (Igor) is installed → allow normal inventory/runtime to auto-build.
  3. If GameMaker source with no runnable build and IDE is missing → soft-pause
     BEFORE the AI grading call so the teacher sees an install banner instead
     of a hard fail (GRD-001 / empty JSON).
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence


def _paths_blob(submission_paths: Sequence[str]) -> str:
    return "\n".join(str(p) for p in (submission_paths or []) if p).lower()


def has_runnable_gamemaker_or_exe_build(submission_paths: Sequence[str]) -> bool:
    """True when a real executable / data.win / HTML5 runner is present."""
    paths_l = _paths_blob(submission_paths)
    if re.search(r"(^|[\\/\s])[^\\/\n]*\.exe(\s|$)", paths_l):
        return True
    if re.search(r"(^|[\\/\s])data\.win(\s|$)", paths_l):
        return True
    if re.search(r"(^|[\\/\s])(index|runner)\.html?(\s|$)", paths_l):
        return True
    return False


def has_gamemaker_source_project(submission_paths: Sequence[str]) -> bool:
    paths_l = _paths_blob(submission_paths)
    return bool(
        re.search(r"\.yyp(\s|$)", paths_l)
        or re.search(r"\.gml(\s|$)", paths_l)
        or re.search(r"\.yyz(\s|$)", paths_l)
    )


def gamemaker_ide_tools_available() -> bool:
    try:
        from app.runtime_engines.gamemaker.ide_builder import discover_gamemaker_tools

        return bool((discover_gamemaker_tools() or {}).get("available"))
    except Exception:
        return False


def should_soft_pause_for_missing_gamemaker_ide(
    submission_paths: Sequence[str],
) -> bool:
    """
    Soft-pause when:
      - GameMaker source is present
      - no runnable .exe / data.win / html5
      - GameMaker IDE tools are not on this machine
    """
    if not has_gamemaker_source_project(submission_paths):
        return False
    if has_runnable_gamemaker_or_exe_build(submission_paths):
        return False
    return not gamemaker_ide_tools_available()


def build_gamemaker_install_pause_result(
    *,
    student_info: Dict[str, Any],
    submission_paths: Sequence[str],
    grading_criteria: Optional[List[Dict[str, Any]]] = None,
    grading_mode: str = "pro",
) -> Dict[str, Any]:
    """Return a successful (non-error) paused grading snapshot for the UI/report."""
    message_ar = (
        "⏸ تم إيقاف تصحيح هذا الطالب مؤقتاً.\n"
        "السبب: المشروع مُسلَّم كمصدر GameMaker (بدون ملف تشغيل .exe)، "
        "وبرنامج GameMaker غير مثبت على جهاز التصحيح — لا يمكن بناء اللعبة "
        "وتشغيلها فعلياً.\n"
        "المطلوب: 1) ثبّت GameMaker Studio 2 على هذا الجهاز. "
        "2) أعد الضغط على «بدء التصحيح» / «استمرار» لهذا الطالب. "
        "سيقوم النظام تلقائياً باكتشاف التثبيت، بناء المشروع، تشغيل اللعبة، "
        "وإكمال التصحيح."
    )
    paused_info = {
        "paused": True,
        "reason": "gamemaker_not_installed",
        "short_ar": "⏸ معلّق — ثبّت GameMaker ثم أعد التصحيح",
        "message_ar": message_ar,
        "builder_reason": "gamemaker_runtime_not_installed",
        "policy": "strict_pause_no_alt_evidence_bypass",
        "early_soft_pause": True,
    }
    banner = {
        "active": True,
        "title_ar": "⏸ التصحيح مُعلَّق — يتطلب تثبيت GameMaker",
        "body_ar": message_ar,
    }
    criteria_results: List[Dict[str, Any]] = []
    for row in grading_criteria or []:
        if not isinstance(row, dict):
            continue
        level = str(row.get("level") or row.get("criteria_level") or "").strip()
        if not level:
            continue
        criteria_results.append(
            {
                "criteria_level": level,
                "achieved": False,
                "score": 0,
                "max_score": int(row.get("max_score") or row.get("points") or 0) or 0,
                "feedback": message_ar,
                "reasoning": "التصحيح معلّق بانتظار تثبيت GameMaker وبناء المشروع.",
                "runtime_gate_block": True,
                "award_block_reason": "gamemaker_install_required",
            }
        )

    paths = [str(p) for p in (submission_paths or []) if p]
    ide_build = {
        "attempted": False,
        "success": False,
        "reason": "gamemaker_runtime_not_installed",
        "reason_ar": "GameMaker غير مثبت على جهاز التصحيح.",
        "tools": {"available": False},
        "early_soft_pause": True,
    }
    return {
        "success": True,
        "student_name": student_info.get("name") or "",
        "student_email": student_info.get("email") or "",
        "student_id": student_info.get("student_id") or "",
        "file_path": student_info.get("path") or "",
        "grade_level": "U",
        "percentage": 0,
        "total_score": 0,
        "max_score": 100,
        "criteria_results": criteria_results,
        "overall_feedback": message_ar,
        "strengths": [],
        "improvements": ["ثبّت GameMaker ثم أعد تصحيح هذا الطالب."],
        "ai_likelihood": 0,
        "grading_mode": grading_mode,
        "grading_paused": paused_info,
        "gamemaker_install_pause_banner": banner,
        "submission_paths": paths,
        "artifact_inventory": {
            "intake_relative_paths": paths,
            "gamemaker_ide_build": ide_build,
            "runtime_observation_report": {
                "status": "paused",
                "gamemaker_ide_build": ide_build,
                "observation_summary_ar": message_ar,
            },
        },
        "gamemaker_ide_build": ide_build,
    }
