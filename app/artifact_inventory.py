"""
Artifact-aware evidence ingestion + runtime evidence governance (Phase 1–3).

Principle: presence ≠ authority — no auto-run, no auto-achievement from .exe/.apk.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

EXECUTABLE_ARTIFACT_EXTENSIONS = frozenset(
    {".exe", ".apk", ".aab", ".pck", ".x86_64", ".app", ".ipa"}
)

SOURCE_CODE_EXTENSIONS = frozenset(
    {
        ".py", ".java", ".cs", ".cpp", ".c", ".h", ".js", ".ts", ".html", ".css",
        ".jsx", ".tsx", ".rb", ".go", ".php", ".gml", ".gd", ".lua", ".sql",
        ".yyp", ".yy",  # GameMaker project / resource metadata
    }
)

# Engine/runnable-game signatures come from the shared single-source registry so
# GameMaker / Scratch detection stays in sync across every grading path.
from app.game_engine_signatures import (  # noqa: E402
    GAMEMAKER_BUILD_FILENAMES,
    GAMEMAKER_PROJECT_EXTENSIONS,
    SCRATCH_PROJECT_EXTENSIONS,
)

DOCUMENT_EXTENSIONS = frozenset({".docx", ".doc", ".pdf", ".pptx", ".ppt"})

_MEDIA_EXTENSIONS = frozenset({".mp4", ".avi", ".mov", ".mkv", ".webm", ".m4v"})

_IMAGE_EXTENSIONS = frozenset({".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp"})

_RUNTIME_PATH_MARKERS = (
    "runtime_evidence", "gameplay", "screenshots", "screen_shots", "captures",
    "screen_capture", "testing", "test_results", "سكرينات", "لقطات", "اختبار",
    "صور تشغيل", "تشغيل اللعبة", "playtest", "test_capture",
)

_RUNTIME_NAME_MARKERS = (
    "gameplay", "runtime", "screenshot", "screen_", "ingame", "hud", "menu",
    "level", "pause", "game_over", "سكرين", "لقطة",
)

# Runtime evidence ladder (Phase 6 governance) — level ≠ criterion achieved
RUNTIME_EVIDENCE_LEVELS: Dict[int, Dict[str, str]] = {
    0: {
        "label_ar": "لا أدلة تشغيل",
        "label_en": "no_runtime_evidence",
        "authority": "none",
    },
    1: {
        "label_ar": "ملفات تنفيذية مُرصدَة",
        "label_en": "executable_detected",
        "authority": "artifact_acknowledgment_only",
    },
    2: {
        "label_ar": "لقطات/صور مرشّحة",
        "label_en": "screenshot_candidates",
        "authority": "advisory_visual_inference",
    },
    3: {
        "label_ar": "footage لعب مرشّح",
        "label_en": "gameplay_footage",
        "authority": "advisory_video_inference",
    },
    4: {
        "label_ar": "تشغيل مُلاحَظ (sandbox)",
        "label_en": "runtime_observed",
        "authority": "partial_runtime_observation",
    },
    5: {
        "label_ar": "مراجعة بشرية موثّقة",
        "label_en": "human_verified_replay",
        "authority": "governed_human_review",
    },
}

# Advisory screenshot → criterion candidate mapping (Phase 3 — inference only)
_SCREENSHOT_INFERENCE_PATTERNS: List[Dict[str, Any]] = [
    {
        "signals": ("main menu", "title screen", "start game", "play button", "قائمة", "ابدأ"),
        "possible_evidence": ["game_launch_evidence"],
        "confidence": "low",
    },
    {
        "signals": ("hud", "score", "health", "lives", "timer", "نقاط", "حياة", "مؤقت"),
        "possible_evidence": ["score_system", "lives_system", "timer_system", "ui_hud"],
        "confidence": "low",
    },
    {
        "signals": ("game over", "you died", "level complete", "victory", "خسارة", "فوز", "مستوى"),
        "possible_evidence": ["gameplay_progression", "lives_system"],
        "confidence": "low",
    },
    {
        "signals": ("pause", "settings", "options", "إيقاف", "إعدادات"),
        "possible_evidence": ["interaction_system", "ui_menus"],
        "confidence": "low",
    },
    {
        "signals": ("platform", "jump", "collision", "enemy", "player", "قفز", "عدو", "لاعب"),
        "possible_evidence": ["platformer_mechanics", "collision_system"],
        "confidence": "low",
    },
]


def _existing_files(paths: Optional[List[str]]) -> List[Path]:
    out: List[Path] = []
    for raw in paths or []:
        try:
            p = Path(raw)
            if p.is_file():
                out.append(p)
        except (OSError, ValueError):
            continue
    return out


def _resolve_inventory_paths(
    submission_paths: Optional[List[str]],
    *,
    main_document_path: Optional[str] = None,
    student_name: str = "",
    grading_mode: str = "deep",
) -> List[str]:
    """Expand disk tree so inventory matches files the grader can read."""
    paths = list(submission_paths or [])
    try:
        from app.evidence_completeness_gate import expand_submission_paths

        primary = main_document_path or (paths[0] if paths else "")
        return expand_submission_paths(
            paths,
            primary_path=primary or "",
            student_name=student_name or "",
            grading_mode=grading_mode,
        )
    except Exception:
        return paths


def build_minimal_artifact_inventory(
    *,
    submission_paths: Optional[List[str]] = None,
    main_document_path: Optional[str] = None,
    embedded_image_count: int = 0,
    vision_analysis_used: bool = False,
    vision_extracted_count: int = 0,
    grading_mode: str = "fast",
) -> Dict[str, Any]:
    """Fast path-only inventory for BASIC — no tree walk, no runtime."""
    paths = list(submission_paths or [])
    doc_n = code_n = 0
    code_names: List[str] = []
    for raw in paths[:80]:
        try:
            p = Path(raw)
            if not p.is_file():
                continue
            ext = p.suffix.lower()
            if ext in DOCUMENT_EXTENSIONS:
                doc_n += 1
            elif ext in SOURCE_CODE_EXTENSIONS:
                code_n += 1
                if len(code_names) < 12:
                    code_names.append(p.name)
        except OSError:
            continue
    has_code = code_n > 0
    if vision_analysis_used:
        _vision_note = (
            f"وضع BASIC — تقييم من المستند والكود؛ "
            f"Vision لـ {vision_extracted_count} صورة مضمّنة في Word/PDF؛ "
            "لم يُشغَّل Runtime."
        )
        _shot_status = "analyzed"
    else:
        _vision_note = (
            "وضع BASIC — تقييم من المستند والكود؛ "
            "لم يُشغَّل Runtime"
            + (
                f" (وُجدت {embedded_image_count} صورة مضمّنة — لم تُحلَّل)."
                if embedded_image_count
                else "."
            )
        )
        _shot_status = (
            "detected_not_used_in_grading" if embedded_image_count else "not_detected"
        )
    return {
        "version": 2,
        "grading_mode_note_ar": _vision_note,
        "has_executable_artifacts": False,
        "has_source_code_artifacts": has_code,
        "documentation": {"status": "analyzed" if doc_n else "not_detected", "file_count": doc_n},
        "source_code": {
            "status": "analyzed" if has_code else "not_detected",
            "files": [{"name": n} for n in code_names],
        },
        "embedded_screenshots": {
            "status": _shot_status,
            "count": embedded_image_count,
            "vision_analyzed_count": vision_extracted_count if vision_analysis_used else 0,
        },
        "runtime_observation_report": {
            "status": "skipped_fast_mode",
            "reason_ar": "وضع BASIC",
        },
        "runtime_evidence_level": {"level": 0, "label_ar": "مستند/كود فقط", "authority": "documentary"},
        "evidence_authority_note_ar": (
            "ملفات exe/data.win غير مُدرجة في مسار BASIC لتسريع التصحيح؛ "
            "يُقيَّم من Word وملفات GML/GD الظاهرة في الأرشيف."
        ),
        "authority_mapping": {"version": 1, "skipped_fast_mode": True},
        "cross_artifact_consistency": {"version": 1, "skipped_fast_mode": True},
        "l2_l3_corroborative_runtime": {"version": 1, "skipped_fast_mode": True},
    }


def _augment_godot_export_source_files(
    source_files: List[Dict[str, Any]],
    files: List[Path],
    *,
    skip_pck_analysis: bool = False,
) -> List[Dict[str, Any]]:
    """When only Godot export (.pck/.exe) is present, record embedded GDScript evidence."""
    has_gd_evidence = any(
        (f.get("ext") or "").lower() == ".gd"
        or (f.get("source_kind") == "godot_pck_embedded")
        for f in source_files
    )
    if has_gd_evidence or skip_pck_analysis:
        return source_files
    try:
        from app.runtime_observation_sandbox import analyze_godot_pck
    except Exception:
        return source_files

    pcks = sorted(
        (fp for fp in files if fp.suffix.lower() == ".pck"),
        key=lambda p: p.stat().st_size if p.is_file() else 0,
        reverse=True,
    )
    for pck in pcks[:3]:
        try:
            analysis = analyze_godot_pck(pck)
        except Exception:
            continue
        signals = analysis.get("signals") or {}
        if not analysis.get("valid"):
            continue
        if not signals.get("has_gdscript") and not signals.get("has_scenes"):
            continue
        hits = int(signals.get("gd_script_hits") or 0)
        source_files.append(
            {
                "name": f"{pck.name} (Godot export — GDScript/scenes in pack)",
                "path": str(pck.resolve()),
                "ext": ".pck",
                "size_bytes": pck.stat().st_size,
                "source_kind": "godot_pck_embedded",
                "gd_script_hits": hits,
                "scene_hits": int(signals.get("scene_hits") or 0),
            }
        )
        break
    return source_files


def _path_blob(files: List[Path]) -> str:
    return "\n".join(str(fp).replace("\\", "/").lower() for fp in files)


def _path_suggests_runtime_asset(fp: Path) -> bool:
    blob = str(fp).replace("\\", "/").lower()
    if any(m in blob for m in _RUNTIME_PATH_MARKERS):
        return True
    name = fp.name.lower()
    return any(m in name for m in _RUNTIME_NAME_MARKERS)


def _detect_unity_build(files: List[Path]) -> Dict[str, Any]:
    blob = _path_blob(files)
    data_dirs: set = set()
    build_dirs: set = set()
    unity_player_dll = False
    globalgamemanagers = False
    managed_dir = False
    for fp in files:
        for part in fp.parts:
            if part.endswith("_Data"):
                data_dirs.add(part)
            if part.lower() == "build":
                build_dirs.add(part)
            if part.lower() == "managed":
                managed_dir = True
        if fp.name.lower() == "unityplayer.dll":
            unity_player_dll = True
        if fp.name.lower() == "globalgamemanagers":
            globalgamemanagers = True
    has_data = bool(data_dirs) or "_data/" in blob or "\\_data\\" in blob.replace("/", "\\")
    has_build = bool(build_dirs) or "/build/" in blob
    unity_exe = [
        fp for fp in files
        if fp.suffix.lower() == ".exe"
        and (
            (fp.parent / f"{fp.stem}_Data").exists()
            or has_data
            or unity_player_dll
        )
    ]
    detected = has_data or has_build or unity_player_dll or globalgamemanagers
    confidence = "none"
    if detected:
        confidence = "high" if (has_data and (unity_player_dll or globalgamemanagers)) else "medium"
    return {
        "detected": detected,
        "unity_data_folder": has_data,
        "build_folder": has_build,
        "unity_player_dll": unity_player_dll,
        "globalgamemanagers": globalgamemanagers,
        "managed_dir": managed_dir,
        "executable_with_data": len(unity_exe) > 0,
        "confidence": confidence,
    }


def _detect_godot_export(files: List[Path]) -> Dict[str, Any]:
    pck = [fp for fp in files if fp.suffix.lower() == ".pck"]
    x86 = [fp for fp in files if fp.suffix.lower() in {".x86_64", ".exe"} and "godot" in str(fp).lower()]
    has_project = any(fp.name.lower() == "project.godot" for fp in files)
    return {
        "detected": bool(pck or x86 or has_project),
        "pck_files": [f.name for f in pck[:6]],
        "export_binaries": [f.name for f in x86[:4]],
        "project_godot": has_project,
        "confidence": "high" if pck else ("medium" if has_project else "low"),
    }


def _detect_gamemaker(files: List[Path]) -> Dict[str, Any]:
    """GameMaker Studio project (.yyp/.gml) and/or exported build (data.win [+ runner .exe])."""
    yyp = [fp for fp in files if fp.suffix.lower() == ".yyp"]
    yyz = [fp for fp in files if fp.suffix.lower() == ".yyz"]
    gml = [fp for fp in files if fp.suffix.lower() == ".gml"]
    data_win = [fp for fp in files if fp.name.lower() == "data.win"]
    # GameMaker runner exe sits beside data.win
    runner_exe = [
        fp for fp in files
        if fp.suffix.lower() == ".exe" and any(d.parent == fp.parent for d in data_win)
    ]
    project_present = bool(yyp or yyz or gml)
    build_present = bool(data_win)
    detected = project_present or build_present
    confidence = "none"
    if build_present or yyp or yyz:
        confidence = "high"
    elif gml:
        confidence = "medium"
    return {
        "detected": detected,
        "project_present": project_present,
        "build_present": build_present,
        "data_win_present": build_present,
        "runner_exe_present": bool(runner_exe),
        "yyp_count": len(yyp),
        "gml_count": len(gml),
        "confidence": confidence,
    }


def _detect_scratch(files: List[Path]) -> Dict[str, Any]:
    """Scratch playable project (.sb3 / .sb2) — a self-contained runnable game."""
    sb = [fp for fp in files if fp.suffix.lower() in SCRATCH_PROJECT_EXTENSIONS]
    return {
        "detected": bool(sb),
        "project_files": [f.name for f in sb[:6]],
        "sb3_present": any(f.suffix.lower() == ".sb3" for f in sb),
        "confidence": "high" if any(f.suffix.lower() == ".sb3" for f in sb)
        else ("medium" if sb else "none"),
    }


def _detect_html5_build(files: List[Path]) -> Dict[str, Any]:
    html_files = [fp for fp in files if fp.name.lower() == "index.html"]
    wasm = [fp for fp in files if fp.suffix.lower() == ".wasm"]
    js_game = [fp for fp in files if fp.suffix.lower() == ".js" and any(
        k in fp.name.lower() for k in ("game", "phaser", "playcanvas")
    )]
    parent_dirs = {fp.parent for fp in html_files}
    paired_wasm = any(
        any(w.parent == d for w in wasm) for d in parent_dirs
    ) if html_files else False
    return {
        "detected": bool(html_files and (wasm or js_game)),
        "index_html_count": len(html_files),
        "wasm_present": bool(wasm),
        "wasm_paired_with_index": paired_wasm,
        "confidence": "medium" if paired_wasm else ("low" if html_files else "none"),
    }


def _collect_screenshot_candidates(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    try:
        from app.l2_l3_corroborative_runtime import classify_l2_folder_screenshot
    except ImportError:
        classify_l2_folder_screenshot = None  # type: ignore[assignment,misc]

    for fp in files:
        if fp.suffix.lower() not in _IMAGE_EXTENSIONS:
            continue
        l2_meta = classify_l2_folder_screenshot(fp) if classify_l2_folder_screenshot else None
        if l2_meta:
            out.append(l2_meta)
            continue
        if _path_suggests_runtime_asset(fp):
            out.append({
                "name": fp.name,
                "path": str(fp),
                "source": "folder_path_heuristic",
                "tier": "L2",
                "authority": "advisory_corroborative_only",
            })
    return out[:40]


def _collect_gameplay_videos(files: List[Path]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for fp in files:
        if fp.suffix.lower() not in _MEDIA_EXTENSIONS:
            continue
        blob = str(fp).replace("\\", "/").lower()
        is_gameplay = any(
            k in blob for k in ("gameplay", "playthrough", "recording", "demo", "game", "لعب")
        ) or _path_suggests_runtime_asset(fp)
        out.append({
            "name": fp.name,
            "path": str(fp),
            "gameplay_candidate": is_gameplay,
            "status": "detected_not_analyzed",
        })
    return out[:10]


def build_runtime_artifacts_summary(
    files: List[Path],
    project_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Phase 1 — structured runtime artifact awareness block."""
    exe_files = [fp for fp in files if fp.suffix.lower() in EXECUTABLE_ARTIFACT_EXTENSIONS]
    scratch_files = [fp for fp in files if fp.suffix.lower() in SCRATCH_PROJECT_EXTENSIONS]
    apk = any(fp.suffix.lower() in {".apk", ".aab"} for fp in exe_files)
    pck = any(fp.suffix.lower() == ".pck" for fp in exe_files)
    unity = _detect_unity_build(files)
    godot = _detect_godot_export(files)
    gamemaker = _detect_gamemaker(files)
    scratch = _detect_scratch(files)
    html5 = _detect_html5_build(files)
    videos = _collect_gameplay_videos(files)
    screenshots = _collect_screenshot_candidates(files)

    profile = project_profile or {}
    rt = profile.get("runtime_evidence") or {}
    unity_semantic = profile.get("unity_semantic") or {}
    unity_source_present = bool(
        (unity_semantic.get("scripts_analyzed") or 0) > 0
        or (unity_semantic.get("assets_peeked") or 0) > 0
        or (unity_semantic.get("monobehaviour_count") or 0) > 0
    )
    profile_shots = rt.get("screenshot_candidates") or []
    profile_videos = rt.get("video_files") or rt.get("video_paths") or []

    if profile_shots and not screenshots:
        for item in profile_shots[:20]:
            if isinstance(item, dict):
                screenshots.append({
                    "name": item.get("basename") or Path(str(item.get("path", ""))).name,
                    "path": item.get("path", ""),
                    "source": "project_profile",
                })

    return {
        "executables_detected": len(exe_files) > 0 or bool(scratch.get("detected")),
        "apk_detected": apk,
        "pck_detected": pck,
        "godot_export_detected": godot.get("detected", False),
        "unity_build_detected": unity.get("detected", False),
        "gamemaker_detected": gamemaker.get("detected", False),
        "gamemaker_build_detected": gamemaker.get("build_present", False),
        "scratch_detected": scratch.get("detected", False),
        "html5_build_detected": html5.get("detected", False),
        "gameplay_video_detected": bool(videos) or bool(profile_videos),
        "screenshot_folder_detected": len(screenshots) > 0,
        "runtime_verified": False,
        "runtime_observation": "unavailable",
        "gameplay_inference": "limited",
        "executable_files": [
            {"name": f.name, "path": str(f)}
            for f in (exe_files + scratch_files)[:12]
        ],
        "gameplay_videos": videos,
        "screenshot_candidates": screenshots[:20],
        "unity_signals": unity,
        "unity_source_signals": {
            "source_present": unity_source_present,
            "scripts_analyzed": unity_semantic.get("scripts_analyzed", 0),
            "assets_peeked": unity_semantic.get("assets_peeked", 0),
            "monobehaviour_count": unity_semantic.get("monobehaviour_count", 0),
        },
        "unity_source_build_alignment": (
            "source_and_build_present"
            if unity_source_present and unity.get("detected")
            else "source_without_build"
            if unity_source_present
            else "build_without_source"
            if unity.get("detected")
            else "not_applicable"
        ),
        "godot_signals": godot,
        "gamemaker_signals": gamemaker,
        "scratch_signals": scratch,
        "html5_signals": html5,
    }


def compute_runtime_evidence_level(
    inventory: Dict[str, Any],
    project_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Phase 6 — evidence ladder. Level describes what we KNOW, not what we VERIFY.
    Max level without sandbox/human review is 3 (footage inference).
    """
    rt = inventory.get("runtime_artifacts") or {}
    level = 0

    if (
        rt.get("executables_detected")
        or rt.get("unity_build_detected")
        or rt.get("html5_build_detected")
        or rt.get("gamemaker_detected")
        or rt.get("gamemaker_build_detected")
        or rt.get("scratch_detected")
    ):
        level = max(level, 1)

    emb = inventory.get("embedded_screenshots") or {}
    folder_shots = rt.get("screenshot_candidates") or []
    advisory = inventory.get("screenshot_intelligence") or {}
    has_visual = (
        (emb.get("count") or 0) > 0
        or len(folder_shots) > 0
        or len(advisory.get("items") or []) > 0
    )
    if has_visual:
        level = max(level, 2)

    videos = rt.get("gameplay_videos") or []
    profile = project_profile or {}
    rt_profile = profile.get("runtime_evidence") or {}
    video_frames = rt_profile.get("video_frame_count") or 0
    gvi = inventory.get("gameplay_video_inference") or {}
    hints = (gvi.get("video_analysis") or {}).get("runtime_hints") or []
    if videos or video_frames > 0 or (gvi.get("frames_sampled") or 0) > 0:
        level = max(level, 3)
    elif hints:
        level = max(level, 3)

    # Levels 4–5 reserved — never auto-assigned by ingestion
    obs_report = inventory.get("runtime_observation_report") or {}
    if obs_report.get("status") == "completed":
        obs_level = int(obs_report.get("runtime_evidence_level") or 0)
        if obs_level >= 4:
            level = max(level, 4)
        elif obs_level >= 3:
            level = max(level, 3)

    meta = RUNTIME_EVIDENCE_LEVELS.get(min(level, 4), RUNTIME_EVIDENCE_LEVELS[0])
    return {
        "level": level,
        "label_ar": meta["label_ar"],
        "label_en": meta["label_en"],
        "authority": meta["authority"],
        "max_auto_level": 3,
        "note_ar": (
            "مستوى الأدلة يصف ما رُصد/حُلّل — **لا يمنح** Achieved تلقائياً لأي معيار."
        ),
    }


def build_screenshot_intelligence_advisory(
    *,
    vision_analysis_text: str = "",
    embedded_image_count: int = 0,
    screenshot_candidates: Optional[List[Dict[str, Any]]] = None,
    source_code_files: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Phase 3 — advisory gameplay inference from Vision text + path heuristics.
    Never upgrades to runtime_verified.
    """
    items: List[Dict[str, Any]] = []
    text_lower = (vision_analysis_text or "").lower()

    if embedded_image_count > 0 and vision_analysis_text.strip():
        seen_evidence: set = set()
        for pattern in _SCREENSHOT_INFERENCE_PATTERNS:
            if not any(sig in text_lower for sig in pattern["signals"]):
                continue
            for ev in pattern["possible_evidence"]:
                if ev in seen_evidence:
                    continue
                seen_evidence.add(ev)
                corroborated: List[str] = []
                for src in source_code_files or []:
                    name = str(src.get("name", "")).lower()
                    if any(k in name for k in (".cs", ".gd", ".gml", "player", "hud", "game")):
                        corroborated.append(src.get("name", ""))
                items.append({
                    "source": "embedded_document_vision",
                    "image": f"{embedded_image_count} embedded image(s)",
                    "possible_evidence": [ev],
                    "confidence": pattern["confidence"],
                    "corroborated_by": corroborated[:4],
                    "mode": "advisory_gameplay_inference",
                })

    for shot in screenshot_candidates or []:
        name = str(shot.get("name") or shot.get("basename") or "").lower()
        path_str = str(shot.get("path") or "")
        candidates: List[str] = []
        if shot.get("source") == "folder_gameplay_evidence_path" or shot.get("tier") == "L2":
            candidates.append("visual_runtime_activity_suggested")
        if any(k in name for k in ("menu", "title", "start")):
            candidates.append("game_launch_evidence")
        if any(k in name for k in ("hud", "score", "ui")):
            candidates.append("ui_hud")
        if any(k in name for k in ("level", "gameplay", "play")):
            candidates.append("gameplay_progression")
        if not candidates and path_str:
            try:
                from app.l2_l3_corroborative_runtime import path_in_l2_evidence_folder

                if path_in_l2_evidence_folder(Path(path_str)):
                    candidates.append("gameplay_scene_plausible")
            except ImportError:
                pass
        if candidates:
            items.append({
                "source": shot.get("source") or "folder_screenshot_heuristic",
                "image": shot.get("name") or shot.get("basename", ""),
                "possible_evidence": candidates,
                "confidence": "low",
                "corroborated_by": [],
                "mode": "advisory_gameplay_inference",
                "tier": shot.get("tier") or "L2",
                "authority": "advisory_corroborative_only",
            })

    return {
        "version": 1,
        "mode": "advisory_only",
        "runtime_verified": False,
        "items": items[:25],
        "note_ar": (
            "استدلال بصري **استشاري** — ليس تحقق تشغيل ولا سلطة معيار."
        ),
    }


def _testing_evidence_status(
    doc_files: List[Dict[str, Any]],
    embedded_image_count: int,
    runtime_artifacts: Dict[str, Any],
) -> str:
    """Partial if docs mention testing but no runtime verification."""
    has_testing_paths = any(
        "test" in str(f.get("path", "")).lower() or "اختبار" in str(f.get("path", ""))
        for f in doc_files
    )
    if has_testing_paths or embedded_image_count > 0:
        if not runtime_artifacts.get("runtime_verified"):
            return "partial"
    if has_testing_paths:
        return "partial"
    return "not_detected"


def _inventory_runtime_verified(inventory: Dict[str, Any]) -> bool:
    """True when L4 sandbox reported verified runtime (stronger than video hints)."""
    obs = inventory.get("runtime_observation_report") or {}
    if obs.get("runtime_verified") is True:
        return True
    exe = inventory.get("executable_artifacts") or {}
    if exe.get("runtime_verified") is True:
        return True
    rv = inventory.get("runtime_verification") or {}
    if rv.get("verified") is True:
        return True
    return False


def _attach_gameplay_video_inference(
    inventory: Dict[str, Any],
    *,
    files: List[Path],
    source_files: List[Dict[str, Any]],
    screenshot_intel: Dict[str, Any],
    profile_rt: Any,
    skip_heavy_enrichment: bool,
    skip_when_runtime_verified: bool,
) -> Dict[str, Any]:
    if skip_heavy_enrichment:
        return {
            "version": 1,
            "videos_analyzed": 0,
            "video_analysis": {},
            "temporal_evidence_authority": {},
            "skipped_fast_mode": True,
        }
    if skip_when_runtime_verified and _inventory_runtime_verified(inventory):
        print(
            "⏭️ [GAMEPLAY-VIDEO] skipped — runtime_verified "
            "(Pro keeps Runtime evidence; video L3 is advisory-only)"
        )
        return {
            "version": 1,
            "videos_analyzed": 0,
            "video_analysis": {},
            "temporal_evidence_authority": {},
            "skipped_runtime_verified": True,
            "note_ar": (
                "تُخطّى تحليل فيديو اللعب — Runtime تحقق من التشغيل (أقوى من L3 الاستشاري)."
            ),
        }
    try:
        from app.gameplay_video_inference import analyze_gameplay_video_hints

        return analyze_gameplay_video_hints(
            files,
            source_files=source_files,
            screenshot_intel_items=screenshot_intel.get("items"),
            existing_video_evidence=profile_rt if isinstance(profile_rt, dict) else None,
        )
    except Exception:
        return {
            "version": 1,
            "videos_analyzed": 0,
            "video_analysis": {},
            "temporal_evidence_authority": {},
        }


def build_artifact_inventory(
    *,
    main_document_path: Optional[str] = None,
    submission_paths: Optional[List[str]] = None,
    embedded_image_count: int = 0,
    vision_analysis_used: bool = False,
    vision_analysis_text: str = "",
    vision_extracted_count: int = 0,
    project_profile: Optional[Dict[str, Any]] = None,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    student_name: str = "",
    skip_runtime_observation: bool = False,
    skip_heavy_enrichment: bool = False,
    skip_l2_l3_corroborative: bool = False,
    skip_governance_graphs: bool = False,
    skip_gameplay_video_when_runtime_verified: bool = False,
    minimal_mode: bool = False,
    grading_mode: str = "deep",
) -> Dict[str, Any]:
    """Build governance-safe artifact inventory for a submission."""
    if minimal_mode:
        return build_minimal_artifact_inventory(
            submission_paths=submission_paths,
            main_document_path=main_document_path,
            embedded_image_count=embedded_image_count,
            vision_analysis_used=vision_analysis_used,
            vision_extracted_count=vision_extracted_count,
            grading_mode=grading_mode,
        )
    expanded_paths = _resolve_inventory_paths(
        submission_paths,
        main_document_path=main_document_path,
        student_name=student_name,
        grading_mode=grading_mode,
    )
    files = _existing_files(expanded_paths)
    main_path = Path(main_document_path) if main_document_path else None

    doc_files: List[Dict[str, Any]] = []
    source_files: List[Dict[str, Any]] = []
    executable_files: List[Dict[str, Any]] = []
    media_files: List[Dict[str, Any]] = []

    for fp in files:
        ext = fp.suffix.lower()
        entry = {
            "name": fp.name,
            "path": str(fp),
            "ext": ext,
            "size_bytes": fp.stat().st_size,
        }
        if ext in DOCUMENT_EXTENSIONS:
            doc_files.append(entry)
        elif ext in SOURCE_CODE_EXTENSIONS:
            source_files.append(entry)
        elif ext in EXECUTABLE_ARTIFACT_EXTENSIONS:
            executable_files.append(entry)
        elif ext in SCRATCH_PROJECT_EXTENSIONS:
            executable_files.append({**entry, "artifact_kind": "scratch_project"})
            source_files.append({**entry, "source_kind": "scratch_project"})
        elif ext in _MEDIA_EXTENSIONS:
            media_files.append(entry)

    source_files = _augment_godot_export_source_files(
        source_files,
        files,
        skip_pck_analysis=skip_heavy_enrichment,
    )

    if main_path and main_path.is_file() and not any(
        d["path"] == str(main_path) for d in doc_files
    ):
        doc_files.insert(
            0,
            {
                "name": main_path.name,
                "path": str(main_path),
                "ext": main_path.suffix.lower(),
                "size_bytes": main_path.stat().st_size,
            },
        )

    runtime_artifacts = build_runtime_artifacts_summary(files, project_profile)
    has_executables = runtime_artifacts.get("executables_detected", False)
    has_html5_build = runtime_artifacts.get("html5_build_detected", False)
    has_godot_project = runtime_artifacts.get("godot_export_detected", False)
    has_unity_targets = runtime_artifacts.get("unity_build_detected", False) or bool(
        (runtime_artifacts.get("unity_source_signals") or {}).get("source_present")
    )
    has_l4_sandbox_targets = (
        has_executables or has_html5_build or has_godot_project or has_unity_targets
    )
    has_source = len(source_files) > 0

    if embedded_image_count > 0:
        screenshot_status = "analyzed" if vision_analysis_used else "detected_not_used_in_grading"
    elif runtime_artifacts.get("screenshot_folder_detected"):
        l2_chain = (project_profile or {}).get("runtime_evidence") or {}
        l2_n = len(l2_chain.get("screenshot_candidates") or [])
        screenshot_status = (
            "ingested_l2_corroborative" if l2_n > 0 else "detected_not_analyzed"
        )
    else:
        screenshot_status = "not_detected"

    screenshot_intel = build_screenshot_intelligence_advisory(
        vision_analysis_text=vision_analysis_text if vision_analysis_used else "",
        embedded_image_count=embedded_image_count,
        screenshot_candidates=runtime_artifacts.get("screenshot_candidates"),
        source_code_files=source_files,
    )

    profile_rt = (project_profile or {}).get("runtime_evidence")
    # Gameplay video runs after runtime when PRO may skip it if runtime_verified.
    gameplay_video_inference: Dict[str, Any] = {
        "version": 1,
        "videos_analyzed": 0,
        "video_analysis": {},
        "temporal_evidence_authority": {},
        "deferred_until_after_runtime": not skip_heavy_enrichment,
    }

    testing_status = _testing_evidence_status(doc_files, embedded_image_count, runtime_artifacts)
    video_analyzed = False
    media_status = "detected_not_analyzed" if media_files else "not_detected"

    inventory: Dict[str, Any] = {
        "version": 2,
        "documentation": {
            "status": "analyzed" if doc_files else "not_detected",
            "files": doc_files,
        },
        "embedded_screenshots": {
            "status": screenshot_status,
            "count": embedded_image_count,
        },
        "source_code": {
            "status": "analyzed" if has_source else "not_detected",
            "files": source_files,
        },
        "executable_artifacts": {
            "status": "detected_not_executed" if has_executables else "not_detected",
            "files": executable_files,
            "runtime_verified": False,
            "runtime_observation": "unavailable",
            "gameplay_inference": "limited",
        },
        "media_artifacts": {
            "status": media_status,
            "files": media_files,
        },
        "runtime_artifacts": runtime_artifacts,
        "screenshot_intelligence": screenshot_intel,
        "gameplay_video_inference": gameplay_video_inference,
        "testing_evidence": {
            "status": testing_status,
        },
        "runtime_verification": {
            "status": "unavailable",
        },
        "has_executable_artifacts": has_executables,
        "has_source_code_artifacts": has_source,
        "has_runtime_candidates": (
            has_executables
            or runtime_artifacts.get("gameplay_video_detected")
            or runtime_artifacts.get("screenshot_folder_detected")
            or embedded_image_count > 0
        ),
    }

    inventory["runtime_evidence_level"] = compute_runtime_evidence_level(
        inventory, project_profile
    )

    if has_executables:
        sample = ", ".join(
            f["name"] for f in (runtime_artifacts.get("executable_files") or executable_files)[:4]
        )
        inventory["evidence_authority_note_ar"] = (
            f"تم رصد ملفات تنفيذية/تصدير ({sample}) ضمن التسليم، "
            "لكن النظام **لم يشغّلها** ولم يتحقق من التشغيل الفعلي. "
            "التقييم يعتمد على التوثيق والأدلة الساكنة — "
            "وجود الملف لا يمنح سلطة إثبات أن اللعبة تعمل أو تحقق المعيار."
        )
    elif inventory["has_runtime_candidates"]:
        inventory["evidence_authority_note_ar"] = (
            "وُجدت مرشّحات أدلة تشغيل (لقطات/فيديو/بناء) — "
            "تمت معالجتها كـ **استدلال استشاري** دون تحقق تشغيل."
        )
    elif runtime_artifacts.get("scratch_detected"):
        sample = ", ".join(
            f["name"]
            for f in (runtime_artifacts.get("executable_files") or executable_files)[:3]
        )
        inventory["evidence_authority_note_ar"] = (
            f"تم رصد مشروع Scratch قابل للتشغيل ({sample}) — "
            "لم يُتحقق من التشغيل الفعلي على الخادم بعد."
        )
    else:
        inventory["evidence_authority_note_ar"] = (
            "لم يُرصد أي ملف تنفيذي (.exe/.apk/.pck) أو build واضح ضمن مسارات التسليم."
        )

    inventory["evidence_coverage_matrix"] = build_evidence_coverage_matrix(inventory)

    _skip_all_governance = skip_heavy_enrichment
    _skip_graphs_only = skip_governance_graphs and not skip_heavy_enrichment
    try:
        if _skip_all_governance:
            inventory.setdefault("authority_mapping", {"version": 1, "by_type": [], "skipped_fast_mode": True})
            inventory.setdefault(
                "cross_artifact_consistency",
                {"version": 1, "ambiguities": [], "ambiguity_count": 0, "skipped_fast_mode": True},
            )
            inventory.setdefault(
                "temporal_consistency",
                {"version": 1, "temporal_consistency_signals": [], "signal_count": 0, "skipped_fast_mode": True},
            )
            inventory.setdefault(
                "evidence_trace_graph",
                {"version": 1, "nodes": [], "edges": [], "skipped_fast_mode": True},
            )
        else:
            from app.evidence_authority_mapping import build_authority_mapping
            from app.cross_artifact_consistency import build_cross_artifact_consistency_report

            inventory["authority_mapping"] = build_authority_mapping(
                inventory, project_profile=project_profile
            )
            inventory["cross_artifact_consistency"] = build_cross_artifact_consistency_report(
                inventory,
                submission_paths=expanded_paths,
                project_profile=project_profile,
                vision_analysis_text=vision_analysis_text if vision_analysis_used else "",
            )
            if _skip_graphs_only:
                inventory["temporal_consistency"] = {
                    "version": 1,
                    "temporal_consistency_signals": [],
                    "signal_count": 0,
                    "skipped_pro_governance": True,
                }
                inventory["evidence_trace_graph"] = {
                    "version": 1,
                    "nodes": [],
                    "edges": [],
                    "skipped_pro_governance": True,
                }
            else:
                from app.temporal_consistency_governance import build_temporal_consistency_report
                from app.evidence_trace_graph import build_evidence_trace_graph

                inventory["temporal_consistency"] = build_temporal_consistency_report(
                    inventory, project_profile=project_profile
                )
                inventory["evidence_trace_graph"] = build_evidence_trace_graph(
                    inventory,
                    temporal_consistency=inventory["temporal_consistency"],
                )
    except Exception:
        inventory.setdefault("authority_mapping", {"version": 1, "by_type": []})
        inventory.setdefault(
            "cross_artifact_consistency",
            {"version": 1, "ambiguities": [], "ambiguity_count": 0},
        )
        inventory.setdefault(
            "temporal_consistency",
            {"version": 1, "temporal_consistency_signals": [], "signal_count": 0},
        )
        inventory.setdefault("evidence_trace_graph", {"version": 1, "nodes": [], "edges": []})

    if skip_heavy_enrichment or skip_l2_l3_corroborative:
        inventory["l2_l3_corroborative_runtime"] = {
            "version": 1,
            "entered_chain": False,
            "authority_ceiling": "advisory_corroborative_only",
            "skipped_fast_mode": skip_heavy_enrichment,
            "skipped_pro_corroborative": skip_l2_l3_corroborative and not skip_heavy_enrichment,
        }
    else:
        try:
            from app.l2_l3_corroborative_runtime import build_l2_l3_corroborative_runtime_evidence

            inventory["l2_l3_corroborative_runtime"] = build_l2_l3_corroborative_runtime_evidence(
                inventory, project_profile
            )
        except Exception:
            inventory["l2_l3_corroborative_runtime"] = {
                "version": 1,
                "entered_chain": False,
                "authority_ceiling": "advisory_corroborative_only",
            }

    try:
        from app.runtime_claim_contract import build_runtime_claims_registry

        inventory["runtime_claims_registry"] = build_runtime_claims_registry(
            inventory, project_profile=project_profile
        )
    except Exception:
        inventory["runtime_claims_registry"] = {
            "version": 1,
            "claim_count": 0,
            "claims": [],
            "contract_complete": False,
            "violations": [{"code": "registry_build_failed"}],
        }

    # L4 runtime observation sandbox — gated until GOVERNANCE_FREEZE_v2 + signed verdict
    from app.governance_freeze_registry import is_l4_sandbox_permitted

    if (
        not skip_runtime_observation
        and has_l4_sandbox_targets
        and submission_paths
        and is_l4_sandbox_permitted()
    ):
        try:
            from app.runtime.sandbox_engine import run_sandbox_observation
            from app.runtime.validation_engine import validate_runtime_observation
            from app.grading_mode_policy import grading_flags

            _web_auto = grading_flags(grading_mode).get("enable_web_browser_automation", False)
            _android_auto = grading_flags(grading_mode).get("enable_android_emulator_automation", False)
            _gm_auto = grading_flags(grading_mode).get("enable_gamemaker_runtime_verification", False)
            _scratch_auto = grading_flags(grading_mode).get("enable_scratch_runtime_verification", False)

            _obs = run_sandbox_observation(
                expanded_paths,
                submission_id=submission_id,
                batch_id=batch_id,
                student_name=student_name or "",
                enable_smoke_test=True,
                enable_web_browser_automation=_web_auto,
                enable_android_emulator_automation=_android_auto,
                enable_gamemaker_runtime_verification=_gm_auto,
                enable_scratch_runtime_verification=_scratch_auto,
                grading_mode=grading_mode,
            )
            _obs["runtime_validation"] = validate_runtime_observation(_obs)
            inventory["runtime_observation_report"] = _obs
            inventory["runtime_validation"] = _obs.get("runtime_validation")
            if isinstance(_obs.get("gameplay_verification"), dict):
                inventory["gameplay_verification"] = _obs["gameplay_verification"]
            elif isinstance(_obs.get("artifact_analyses"), list):
                for _aa in _obs["artifact_analyses"]:
                    if isinstance(_aa, dict) and isinstance(
                        _aa.get("gameplay_verification"), dict
                    ):
                        inventory["gameplay_verification"] = _aa["gameplay_verification"]
                        break
            try:
                from app.grading_mode_policy import is_fast_grading_mode

                if is_fast_grading_mode(grading_mode):
                    inventory["grading_mode_note_ar"] = (
                        "وضع STANDARD — Runtime خفيف (تشغيل + sweep قصير، بدون Agent gameplay). "
                        "القواعد الأكاديمية ثابتة؛ الأدلة أقل من PRO."
                    )
            except Exception:
                pass
            if _obs.get("status") == "completed":
                unity_summaries = _obs.get("unity_observation_summary") or []
                visual_summaries = _obs.get("visual_observation_summary") or []
                runtime_screenshots = _obs.get("runtime_screenshots") or []
                if unity_summaries:
                    runtime_artifacts["unity_runtime_observation"] = unity_summaries
                    runtime_artifacts["unity_runtime_observed"] = bool(_obs.get("runtime_observed"))
                    runtime_artifacts["unity_player_log_found"] = any(
                        bool(u.get("player_log_found")) for u in unity_summaries if isinstance(u, dict)
                    )
                    inventory["runtime_artifacts"] = runtime_artifacts
                if visual_summaries or runtime_screenshots:
                    runtime_artifacts["visual_runtime_observation"] = visual_summaries
                    runtime_artifacts["runtime_screenshots"] = runtime_screenshots
                    runtime_artifacts["runtime_screenshot_count"] = sum(
                        1 for shot in runtime_screenshots
                        if isinstance(shot, dict) and shot.get("status") == "captured"
                    )
                    runtime_artifacts["visual_runtime_evidence"] = (
                        "present" if runtime_artifacts["runtime_screenshot_count"] else "unavailable"
                    )
                    runtime_artifacts["black_screen_possible"] = any(
                        shot.get("visual_state") == "black_screen"
                        or ((shot.get("visual_stats") or {}).get("black_screen_possible") is True)
                        for shot in runtime_screenshots
                        if isinstance(shot, dict)
                    )
                    first_visual = visual_summaries[0] if visual_summaries else {}
                    runtime_artifacts["visual_states_observed"] = first_visual.get(
                        "visual_states_observed", []
                    )
                    runtime_artifacts["visual_runtime_confidence"] = first_visual.get(
                        "visual_runtime_confidence", 0.0
                    )
                    runtime_artifacts["freeze_possible"] = first_visual.get(
                        "freeze_possible", False
                    )
                    runtime_artifacts["runtime_session_id"] = _obs.get("runtime_session_id")
                    inventory["runtime_artifacts"] = runtime_artifacts
                    inventory["runtime_visual_evidence"] = {
                        "status": runtime_artifacts["visual_runtime_evidence"],
                        "screenshot_count": runtime_artifacts["runtime_screenshot_count"],
                        "black_screen_possible": runtime_artifacts["black_screen_possible"],
                        "visual_states_observed": runtime_artifacts.get("visual_states_observed", []),
                        "visual_runtime_confidence": runtime_artifacts.get(
                            "visual_runtime_confidence", 0.0
                        ),
                        "freeze_possible": runtime_artifacts.get("freeze_possible", False),
                        "runtime_session_id": _obs.get("runtime_session_id"),
                        "observed_visual_elements": first_visual.get("observed_visual_elements", []),
                        "unverified_gameplay": first_visual.get("unverified_gameplay", []),
                        "human_validation_required": first_visual.get(
                            "human_validation_required", []
                        ),
                        "authority": "advisory_visual_runtime_only",
                        "note_ar": (
                            "لقطات runtime + visual_state استشاريان على ظهور output فقط — "
                            "لا تثبت gameplay correctness."
                        ),
                    }
                exe_block = inventory.get("executable_artifacts") or {}
                exe_block["runtime_verified"] = bool(_obs.get("runtime_verified"))
                exe_block["runtime_observed"] = bool(_obs.get("runtime_observed"))
                exe_block["runtime_observation"] = "completed"
                exe_block["status"] = (
                    "observed_runtime_advisory"
                    if _obs.get("runtime_observed")
                    else "observed_structure_only"
                )
                exe_block["verification_status"] = (
                    "runtime_observed_not_institutionally_verified"
                    if _obs.get("runtime_observed")
                    else "structure_only"
                )
                inventory["executable_artifacts"] = exe_block
                inventory["runtime_verification"] = {
                    "status": "observed_advisory" if _obs.get("runtime_observed") else "partial",
                    "mode": _obs.get("observation_mode"),
                    "verified": bool(_obs.get("runtime_verified")),
                    "human_authority_required": True,
                }
                inventory["runtime_signal_graph"] = _obs.get("runtime_signal_graph")
                restriction_reports = [
                    a.get("process_restriction")
                    for a in (_obs.get("artifact_analyses") or [])
                    if isinstance(a, dict) and a.get("process_restriction")
                ]
                if restriction_reports:
                    inventory["runtime_process_restriction"] = restriction_reports[0]
                    if any(r.get("suspicious_spawn_detected") for r in restriction_reports):
                        runtime_artifacts["suspicious_spawn_detected"] = True
                        inventory["runtime_artifacts"] = runtime_artifacts
                interaction_reports = [
                    a.get("interaction_trace")
                    for a in (_obs.get("artifact_analyses") or [])
                    if isinstance(a, dict) and a.get("interaction_trace")
                ]
                if interaction_reports:
                    inventory["runtime_interaction_trace"] = interaction_reports[0]
                    runtime_artifacts["interaction_trace"] = interaction_reports[0]
                    runtime_artifacts["automated_interaction_observed"] = any(
                        t.get("interaction_traces_detected") for t in interaction_reports
                    )
                    runtime_artifacts["visual_response_to_input"] = next(
                        (
                            t.get("visual_response_to_input")
                            for t in interaction_reports
                            if t.get("visual_response_to_input")
                        ),
                        "unknown",
                    )
                    inventory["runtime_artifacts"] = runtime_artifacts
                inventory["runtime_evidence_level"] = compute_runtime_evidence_level(
                    inventory, project_profile
                )
                sample = ", ".join(
                    f["name"]
                    for f in (runtime_artifacts.get("executable_files") or executable_files)[:3]
                )
                inventory["evidence_authority_note_ar"] = (
                    f"تمت ملاحظة runtime محكومة لـ ({sample}). "
                    f"L{inventory['runtime_evidence_level'].get('level', 4)} — "
                    "**observations collected under controlled conditions** — "
                    "ليست verification مؤسسية نهائية ولا تثبت gameplay correctness."
                )
                inventory["evidence_coverage_matrix"] = build_evidence_coverage_matrix(inventory)
        except Exception as _obs_err:
            inventory["runtime_observation_report"] = {
                "status": "error",
                "error": str(_obs_err),
            }
    elif skip_runtime_observation and has_l4_sandbox_targets:
        inventory["runtime_observation_report"] = {
            "status": "skipped_fast_mode",
            "reason": "basic_grading_mode",
            "gate_ar": "وضع BASIC — لم يُشغَّل Runtime (توفير الوقت).",
        }
    elif has_l4_sandbox_targets and submission_paths:
        inventory["runtime_observation_report"] = {
            "status": "gated",
            "reason": "GOVERNANCE_FREEZE_v1_active",
            "gate_ar": (
                "L4 sandbox مقفول — أكمل Epoch Workshop Review + signed institutional verdict "
                "قبل runtime authority expansion."
            ),
            "decision_package_url": "/governance/l4-decision",
        }

    gameplay_video_inference = _attach_gameplay_video_inference(
        inventory,
        files=files,
        source_files=source_files,
        screenshot_intel=screenshot_intel,
        profile_rt=profile_rt,
        skip_heavy_enrichment=skip_heavy_enrichment,
        skip_when_runtime_verified=skip_gameplay_video_when_runtime_verified,
    )
    inventory["gameplay_video_inference"] = gameplay_video_inference
    _videos_n = gameplay_video_inference.get("videos_analyzed")
    video_analyzed = isinstance(_videos_n, int) and _videos_n > 0
    if video_analyzed:
        inventory["media_artifacts"]["status"] = "analyzed_advisory"
    elif gameplay_video_inference.get("skipped_runtime_verified"):
        inventory["media_artifacts"]["status"] = "runtime_verified_skip_video"
    elif media_files:
        inventory["media_artifacts"]["status"] = "detected_not_analyzed"

    if not skip_heavy_enrichment and not skip_governance_graphs:
        try:
            from app.academic_explainability import attach_academic_explainability

            attach_academic_explainability(
                inventory,
                submission_paths=expanded_paths,
                project_profile=project_profile,
            )
        except Exception:
            inventory.setdefault("governance_intent", {"version": 1})
    else:
        inventory.setdefault(
            "governance_intent",
            {
                "version": 1,
                "skipped_fast_mode": skip_heavy_enrichment,
                "skipped_pro_governance": skip_governance_graphs and not skip_heavy_enrichment,
            },
        )
        inventory.setdefault("missing_evidence_diagnostics", {"version": 1, "rows": []})
        inventory.setdefault("extraction_coverage", {"version": 1})

    return inventory


def build_evidence_coverage_matrix(inventory: Dict[str, Any]) -> List[Dict[str, str]]:
    """Phase 2 — structured table rows for reports (type × coverage × authority)."""
    exec_block = inventory.get("executable_artifacts") or {}
    exec_status = exec_block.get("status") or "not_detected"
    rt = inventory.get("runtime_artifacts") or {}
    rt_level = inventory.get("runtime_evidence_level") or {}
    testing = inventory.get("testing_evidence") or {}
    media = inventory.get("media_artifacts") or {}

    rows = [
        {
            "type_ar": "التوثيق (Word/PDF)",
            "coverage_ar": _status_label((inventory.get("documentation") or {}).get("status")),
            "authority_ar": "تحليل نصي",
        },
        {
            "type_ar": "الصور المضمّنة",
            "coverage_ar": _status_label((inventory.get("embedded_screenshots") or {}).get("status")),
            "authority_ar": "استدلال بصري استشاري",
        },
        {
            "type_ar": "الكود المصدري",
            "coverage_ar": _status_label((inventory.get("source_code") or {}).get("status")),
            "authority_ar": "تحليل ساكن (بدون تشغيل)",
        },
        {
            "type_ar": "ملفات تنفيذية / builds",
            "coverage_ar": _runtime_artifact_coverage(rt, exec_status),
            "authority_ar": (
                "ملاحظة تشغيل استشارية — ليست verification"
                if exec_status == "observed_runtime_advisory"
                else "رُصدت — لم تُشغَّل"
                if exec_status == "detected_not_executed" or rt.get("executables_detected")
                else "غير متوفر"
            ),
        },
        {
            "type_ar": "تشغيل اللعب (gameplay execution)",
            "coverage_ar": "غير مُتحقَّق",
            "authority_ar": "unavailable",
        },
        {
            "type_ar": "فيديو لعب",
            "coverage_ar": _video_coverage_label(inventory),
            "authority_ar": _video_authority_label(inventory),
        },
        {
            "type_ar": "أدلة الاختبار",
            "coverage_ar": _status_label(testing.get("status")),
            "authority_ar": "جزئي — بدون تشغيل" if testing.get("status") == "partial" else "غير متوفر",
        },
        {
            "type_ar": "التحقق من التشغيل",
            "coverage_ar": _status_label((inventory.get("runtime_verification") or {}).get("status")),
            "authority_ar": (
                "ملاحظة تشغيل استشارية — مراجعة بشرية مطلوبة"
                if (inventory.get("runtime_verification") or {}).get("status") == "observed_advisory"
                else "غير متاح"
            ),
        },
        {
            "type_ar": "مستوى أدلة التشغيل",
            "coverage_ar": f"L{rt_level.get('level', 0)} — {rt_level.get('label_ar', '')}",
            "authority_ar": rt_level.get("authority", "none"),
        },
    ]
    return rows


def _runtime_artifact_coverage(rt: Dict[str, Any], exec_status: str) -> str:
    parts: List[str] = []
    if rt.get("executables_detected"):
        parts.append("executables")
    if rt.get("godot_export_detected"):
        parts.append("Godot export")
    if rt.get("unity_build_detected"):
        parts.append("Unity build")
    if rt.get("html5_build_detected"):
        parts.append("HTML5")
    if parts:
        prefix = "لوحظ تشغيلها جزئياً — " if exec_status == "observed_runtime_advisory" else "رُصدت — "
        return prefix + "، ".join(parts)
    return _status_label(exec_status)


def _video_coverage_label(inventory: Dict[str, Any]) -> str:
    gvi = inventory.get("gameplay_video_inference") or {}
    if (gvi.get("frames_sampled") or 0) > 0:
        hints = len((gvi.get("video_analysis") or {}).get("runtime_hints") or [])
        return f"frames مُ sample — {hints} hint(s) — advisory"
    media = inventory.get("media_artifacts") or {}
    rt = inventory.get("runtime_artifacts") or {}
    if media.get("files") or rt.get("gameplay_video_detected"):
        return "رُصد — لم يُحلَّل"
    return "غير موجود"


def _video_authority_label(inventory: Dict[str, Any]) -> str:
    gvi = inventory.get("gameplay_video_inference") or {}
    ta = gvi.get("temporal_evidence_authority") or {}
    if ta.get("temporal_authority_level", 0) > 0:
        return f"temporal L{ta.get('temporal_authority_level')} — advisory"
    rt = inventory.get("runtime_artifacts") or {}
    if rt.get("gameplay_video_detected"):
        return "استدلال استشاري"
    return "غير متوفر"


def _status_label(status: Optional[str]) -> str:
    mapping = {
        "analyzed": "تم التحليل",
        "detected_not_executed": "رُصدت — لم تُشغَّل",
        "detected_not_used_in_grading": "رُصدت — لم تُستخدم في التصحيح",
        "detected_not_analyzed": "رُصدت — لم تُحلَّل",
        "analyzed_advisory": "حُلّل — استشاري (L3)",
        "observed_runtime_advisory": "لوحظ تشغيلها — استشاري",
        "observed_structure_only": "رُصدت بنيتها فقط",
        "observed_advisory": "ملاحظة تشغيل استشارية",
        "partial": "جزئي",
        "not_detected": "غير موجود",
        "unavailable": "غير متاح",
    }
    if not status:
        return "غير معروف"
    return mapping.get(status, status)


def format_artifact_context_for_grading(inventory: Dict[str, Any]) -> str:
    """Bounded epistemic block for the AI grader — presence ≠ authority."""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "[سجل artifacts — runtime evidence governance | presence ≠ authority]",
        "═══════════════════════════════════════════════════════════",
    ]

    rt_level = inventory.get("runtime_evidence_level") or {}
    lines.append(
        f"• مستوى أدلة التشغيل: L{rt_level.get('level', 0)} — "
        f"{rt_level.get('label_ar', '')} (authority: {rt_level.get('authority', 'none')})."
    )

    rt = inventory.get("runtime_artifacts") or {}
    if rt.get("executables_detected"):
        names = ", ".join(
            f.get("name", "") for f in rt.get("executable_files", [])[:6]
        )
        obs = inventory.get("runtime_observation_report") or {}
        if obs.get("status") == "completed":
            lines.append(
                f"• ملفات تنفيذية/build: {names} — **لوحظ تشغيلها جزئياً L4 "
                "لكنها ليست verification نهائية**."
            )
        else:
            lines.append(f"• ملفات تنفيذية/build: {names} — **رُصدت — لم تُشغَّل**.")
    if rt.get("godot_export_detected"):
        lines.append("• Godot export (.pck/project.godot) — **مرشّح runtime — غير مُتحقَّق**.")
    if rt.get("unity_build_detected"):
        unity_obs = rt.get("unity_runtime_observation") or []
        alignment = rt.get("unity_source_build_alignment")
        if unity_obs:
            first = unity_obs[0] if isinstance(unity_obs[0], dict) else {}
            lines.append(
                "• Unity build (*_Data/Build) — **runtime observed advisory**: "
                f"Player.log={bool(first.get('player_log_found'))}, "
                f"Unity={first.get('unity_version_hint') or 'unknown'}, "
                f"errors={first.get('error_count', 0)}, "
                f"crash_signals={first.get('crash_signal_count', 0)}."
            )
        else:
            lines.append("• Unity build (*_Data/Build) — **مرشّح runtime — غير مُتحقَّق**.")
        if alignment == "source_and_build_present":
            lines.append("  • Unity static/runtime alignment: source + build present — تطابق جزئي فقط.")
        elif alignment == "build_without_source":
            lines.append("  • Unity warning: build موجود بدون source واضح — provenance يحتاج مراجعة.")
        elif alignment == "source_without_build":
            lines.append("  • Unity warning: source موجود بدون build تشغيل واضح — runtime يبقى غير مكتمل.")
    elif rt.get("unity_source_build_alignment") == "source_without_build":
        lines.append("• Unity source موجود بدون build تشغيل واضح — runtime يبقى غير مكتمل.")
    if rt.get("runtime_screenshot_count"):
        lines.append(
            f"• Runtime screenshots: {rt.get('runtime_screenshot_count')} captured — "
            f"states={rt.get('visual_states_observed', [])} "
            f"confidence={rt.get('visual_runtime_confidence', 0)} — visual evidence advisory only."
        )
        if rt.get("black_screen_possible"):
            lines.append("  • Visual warning: black screen possible في لقطة واحدة أو أكثر.")
        if rt.get("freeze_possible"):
            lines.append("  • Visual warning: freeze_possible — frames متطابقة تقريباً.")
        rve = inventory.get("runtime_visual_evidence") or {}
        if rve.get("human_validation_required"):
            lines.append(
                "  • Human validation required: "
                + ", ".join(rve.get("human_validation_required")[:4])
            )
    if rt.get("html5_build_detected"):
        lines.append("• HTML5 build (index.html/wasm) — **مرشّح runtime — غير مُتحقَّق**.")
    if rt.get("gameplay_video_detected"):
        lines.append("• فيديو لعب مرشّح — **لم يُستخدم كتحقق تشغيل**.")

    gvi = inventory.get("gameplay_video_inference") or {}
    if (gvi.get("videos_analyzed") or 0) > 0:
        try:
            from app.gameplay_video_inference import format_gameplay_video_inference_for_grading
            gvi_txt = format_gameplay_video_inference_for_grading(gvi)
            if gvi_txt:
                lines.append(gvi_txt.strip())
        except Exception:
            ta = gvi.get("temporal_evidence_authority") or {}
            lines.append(
                f"• L3 video: {gvi.get('frames_sampled')} frames — "
                f"temporal authority L{ta.get('temporal_authority_level', 0)}"
            )

    doc = inventory.get("documentation") or {}
    if doc.get("files"):
        names = ", ".join(f["name"] for f in doc["files"][:5])
        lines.append(f"• التوثيق: {names} — تم تحليل النص.")

    emb = inventory.get("embedded_screenshots") or {}
    if (emb.get("count") or 0) > 0:
        lines.append(
            f"• صور مضمّنة: {emb['count']} — "
            f"الحالة: {_status_label(emb.get('status'))}."
        )

    intel = inventory.get("screenshot_intelligence") or {}
    intel_items = intel.get("items") or []
    if intel_items:
        ev_sample = sorted({
            ev for it in intel_items for ev in (it.get("possible_evidence") or [])
        })[:6]
        lines.append(
            f"• استدلال بصري استشاري (Phase 3): {', '.join(ev_sample)} — "
            "**confidence: low — ليس verification**."
        )

    src = inventory.get("source_code") or {}
    if src.get("files"):
        names = ", ".join(f["name"] for f in src["files"][:6])
        lines.append(f"• كود مصدري: {names} — تحليل ساكن فقط.")

    if rt.get("executables_detected") or inventory.get("has_runtime_candidates"):
        lines.append(
            "  ⛔ لا تقل «لم يُقدّم دليل» — قل: «runtime-capable artifacts مرفقة "
            "لكن بدون runtime verification»."
        )
        lines.append(
            "  ⛔ وجود .exe/.apk/build **لا يثبت** Achieved لـ C.P5/C.P6."
        )
        lines.append(
            "  ⛔ Runtime screenshots إن وُجدت تثبت surface/output فقط — "
            "لا تثبت mechanics أو physics أو win/loss."
        )
    else:
        lines.append("• ملفات تنفيذية/build: لم تُرصد في مسارات التسليم.")

    lines.append(f"• {inventory.get('evidence_authority_note_ar', '')}")

    try:
        from app.academic_explainability import format_explainability_for_grading

        exp_txt = format_explainability_for_grading(inventory)
        if exp_txt:
            lines.append(exp_txt.strip())
    except Exception:
        pass

    tc = inventory.get("temporal_consistency") or {}
    try:
        from app.temporal_consistency_governance import format_temporal_consistency_for_grading
        tc_txt = format_temporal_consistency_for_grading(tc)
        if tc_txt:
            lines.append(tc_txt.strip())
    except Exception:
        pass

    graph = inventory.get("evidence_trace_graph") or {}
    try:
        from app.evidence_trace_graph import format_trace_graph_summary
        gtxt = format_trace_graph_summary(graph)
        if gtxt:
            lines.append(gtxt.strip())
    except Exception:
        pass

    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)


def persist_artifact_inventory_json(
    inventory: Dict[str, Any],
    *,
    student_name: str,
    batch_id: Optional[int] = None,
) -> Optional[str]:
    """Write artifact_inventory.json alongside debug artifacts."""
    try:
        out_dir = Path("uploads/debug")
        out_dir.mkdir(parents=True, exist_ok=True)
        safe = re.sub(r'[^\w\-]+', "_", student_name or "unknown")[:80]
        suffix = f"_batch{batch_id}" if batch_id else ""
        out_path = out_dir / f"{safe}{suffix}_artifact_inventory.json"
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(inventory, f, ensure_ascii=False, indent=2)
        return str(out_path)
    except OSError:
        return None
