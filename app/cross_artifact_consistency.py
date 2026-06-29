"""
Cross-artifact consistency governance — structured ambiguity signals.

Detects contradictions across docs, code, executables, screenshots, and engines.
Does NOT auto-penalize as «student error» — emits consistency_ambiguity only.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_ENGINE_MARKERS = {
    "unity": ("unity", "projectsettings", ".unity", "csharp", "monobehaviour"),
    "godot": ("godot", "project.godot", "gdscript", ".gd", ".tscn"),
    "gamemaker": ("gamemaker", ".yyp", ".gml", "gml"),
    "unreal": ("unreal", ".uasset", "blueprint"),
}


def _engine_signals_from_paths(paths: List[str]) -> Set[str]:
    blob = "\n".join(str(p).replace("\\", "/").lower() for p in paths)
    found: Set[str] = set()
    for engine, markers in _ENGINE_MARKERS.items():
        if any(m in blob for m in markers):
            found.add(engine)
    return found


def _engine_signals_from_profile(project_profile: Optional[Dict[str, Any]]) -> Set[str]:
    if not project_profile:
        return set()
    engines = project_profile.get("engines_detected") or []
    return {str(e).lower() for e in engines if e}


def _executable_base_names(inventory: Dict[str, Any]) -> List[str]:
    rt = inventory.get("runtime_artifacts") or {}
    names: List[str] = []
    for f in rt.get("executable_files") or []:
        base = Path(str(f.get("name", ""))).stem.lower()
        base = re.sub(r"[^a-z0-9\u0600-\u06ff]+", " ", base).strip()
        if base:
            names.append(base)
    for f in (inventory.get("executable_artifacts") or {}).get("files") or []:
        base = Path(str(f.get("name", ""))).stem.lower()
        if base and base not in names:
            names.append(base)
    return names


def _doc_engine_mentions(inventory: Dict[str, Any]) -> Set[str]:
    """Heuristic: scan documentation file names only (bounded)."""
    mentions: Set[str] = set()
    for doc in (inventory.get("documentation") or {}).get("files") or []:
        blob = str(doc.get("name", "")).lower()
        for engine, markers in _ENGINE_MARKERS.items():
            if any(m in blob for m in markers[:2]):
                mentions.add(engine)
    return mentions


def build_cross_artifact_consistency_report(
    inventory: Dict[str, Any],
    *,
    submission_paths: Optional[List[str]] = None,
    project_profile: Optional[Dict[str, Any]] = None,
    vision_analysis_text: str = "",
) -> Dict[str, Any]:
    """
    Formal contradiction / ambiguity resolution layer (advisory).
    """
    paths = list(submission_paths or [])
    path_engines = _engine_signals_from_paths(paths)
    profile_engines = _engine_signals_from_profile(project_profile)
    all_engines = path_engines | profile_engines

    ambiguities: List[Dict[str, Any]] = []
    rt = inventory.get("runtime_artifacts") or {}

    # Multiple engines in same submission
    if len(all_engines) > 1:
        ambiguities.append({
            "code": "cross_engine_artifacts",
            "severity": "medium",
            "engines": sorted(all_engines),
            "message_ar": (
                f"تعارض محتمل: أدلة لعدة محركات ({', '.join(sorted(all_engines))}) — "
                "يُوصى بربط اللقطات/الbuild بالمحرك الموثّق."
            ),
            "resolution": "advisory_hold_corroboration",
        })

    # Godot export + Unity layout
    if rt.get("godot_export_detected") and ("unity" in all_engines):
        ambiguities.append({
            "code": "godot_export_with_unity_signals",
            "severity": "high",
            "message_ar": (
                "Godot export (.pck/project.godot) مع إشارات Unity — "
                "تناقض cross-artifact محتمل."
            ),
            "resolution": "require_explicit_student_explanation",
        })

    # Executable present but no source and no embedded gameplay shots
    if rt.get("executables_detected") and not inventory.get("has_source_code_artifacts"):
        emb = (inventory.get("embedded_screenshots") or {}).get("count") or 0
        intel = len((inventory.get("screenshot_intelligence") or {}).get("items") or [])
        if emb == 0 and intel == 0:
            ambiguities.append({
                "code": "executable_without_corroborating_artifacts",
                "severity": "medium",
                "message_ar": (
                    "ملفات تنفيذية بدون كود مصدري أو لقطات مرشّحة — "
                    "weak linkage (presence only)."
                ),
                "resolution": "do_not_upgrade_authority",
            })

    # Vision mentions engine A, profile says engine B
    vision_lower = (vision_analysis_text or "").lower()
    if vision_lower:
        vision_engines: Set[str] = set()
        if "unity" in vision_lower:
            vision_engines.add("unity")
        if "godot" in vision_lower:
            vision_engines.add("godot")
        if "gamemaker" in vision_lower or "game maker" in vision_lower:
            vision_engines.add("gamemaker")
        if vision_engines and profile_engines and not vision_engines & profile_engines:
            ambiguities.append({
                "code": "vision_engine_mismatch",
                "severity": "high",
                "vision_engines": sorted(vision_engines),
                "profile_engines": sorted(profile_engines),
                "message_ar": (
                    "لقطات/وصف Vision يشير لمحرك مختلف عن ملفات المشروع — "
                    "consistency ambiguity."
                ),
                "resolution": "advisory_not_auto_not_achieved",
            })

    # Multiple distinct executable product names
    exe_names = _executable_base_names(inventory)
    if len(exe_names) >= 2:
        unique_tokens = {n.split()[0] for n in exe_names if n}
        if len(unique_tokens) >= 2:
            ambiguities.append({
                "code": "multiple_product_build_names",
                "severity": "low",
                "names": exe_names[:6],
                "message_ar": (
                    "أسماء builds متعددة (مثلاً farst game / final) — "
                    "قد تشير لنسخ مختلفة؛ لا تُفترض equivalence تلقائياً."
                ),
                "resolution": "document_which_build_was_assessed",
            })

    # Documentation engine mention vs detected engines
    doc_engines = _doc_engine_mentions(inventory)
    if doc_engines and profile_engines and not doc_engines & profile_engines:
        ambiguities.append({
            "code": "documentation_engine_mismatch",
            "severity": "medium",
            "message_ar": "أسماء/مسارات التوثيق لا تطابق محرك المشروع المكتشف.",
            "resolution": "advisory_corroboration_required",
        })

    has_high = any(a.get("severity") == "high" for a in ambiguities)
    return {
        "version": 1,
        "mode": "consistency_ambiguity_signal",
        "engine_signals": sorted(all_engines),
        "ambiguity_count": len(ambiguities),
        "has_unresolved_high_severity": has_high,
        "ambiguities": ambiguities,
        "note_ar": (
            "إشارات ambiguity لا تُترجم تلقائياً إلى Not Achieved — "
            "تُستخدم لضبط claim language وطلب corroboration."
        ),
    }


def format_consistency_report_for_grading(report: Dict[str, Any]) -> str:
    if not report.get("ambiguities"):
        return ""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "[Cross-Artifact Consistency | ambiguity signals — NOT auto-penalty]",
        "═══════════════════════════════════════════════════════════",
    ]
    for amb in report.get("ambiguities") or []:
        lines.append(
            f"• [{amb.get('severity', '?')}] {amb.get('code')}: {amb.get('message_ar', '')}"
        )
    lines.append(
        "• عند التعارض: اذكر ambiguity صراحة — لا تُصدر verdict «كذب» تلقائياً."
    )
    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)
