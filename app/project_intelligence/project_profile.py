"""
Build a compact, model-facing project profile from on-disk submission paths.

Goal: infer engine / project type from folder layout and file presence, not only
extensions. Emit structured evidence + heuristic quality signals — not raw files.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .cross_modal_corroboration import build_cross_modal_corroboration
from .ocr_runtime_extractor import extract_runtime_ocr_evidence
from .runtime_corroboration import build_runtime_corroboration
from .temporal_alignment import build_temporal_alignment
from .ui_token_correlation import build_ui_token_correlation
from .video_runtime_extractor import extract_runtime_video_evidence, list_submission_video_files

_GODOT_PROJECT = "project.godot"
_GAMEMAKER_EXT = ".yyp"
_PACKET_TRACER_EXT = ".pkt"
_EXCEL_SEMANTIC_EXT = frozenset({".xlsx", ".xlsm", ".xltx", ".xltm"})
_PYTHON_ROOT_FILES = {"requirements.txt", "pyproject.toml", "setup.py", "main.py", "app.py"}

_CODE_EXT = {
    ".cs", ".gd", ".gml", ".py", ".js", ".ts", ".java", ".cpp", ".c", ".h",
    ".ino", ".vb", ".rb", ".php", ".swift", ".kt",
}

# Runtime evidence v1: paths / names that suggest gameplay or runtime capture (not every image).
_RUNTIME_SCREENSHOT_EXT = {".png", ".jpg", ".jpeg", ".webp"}
_RUNTIME_PATH_MARKERS = (
    "runtime_evidence",
    "runtime-evidence",
    "runtimeevidence",
    "gameplay",
    "btec_runtime",
    "running_build",
    "captures",
    "screen_capture",
    "screencapture",
    "screenshots",
    "screen_shots",
    "سكرينات",
    "سكرين",
    "لقطات",
    "لقطة",
    "صور تشغيل",
    "تشغيل اللعبة",
    "playtest",
    "test_capture",
)
_RUNTIME_NAME_MARKERS = (
    "gameplay",
    "runtime",
    "capture",
    "screenshot",
    "screen_",
    "ingame",
    "in-game",
    "سكرين",
    "لقطة",
)
_RUNTIME_LOG_BASENAMES = {
    "runtime.log",
    "player.log",
    "unity_player.log",
    "output_log.txt",
    "gameplay.log",
}


def _norm_parts(p: Path) -> Tuple[str, ...]:
    try:
        return tuple(x.lower() for x in p.parts)
    except Exception:
        return tuple()


def _collect_directories_for_paths(paths: List[str]) -> Set[Path]:
    roots: Set[Path] = set()
    for raw in paths:
        try:
            p = Path(raw).resolve()
        except OSError:
            p = Path(raw)
        if p.is_file():
            cur = p.parent
        elif p.is_dir():
            cur = p
        else:
            continue
        for _ in range(10):
            roots.add(cur)
            if cur.parent == cur:
                break
            cur = cur.parent
    return roots


def _path_blob(paths: List[str]) -> str:
    """Single lowercase string of all normalized paths for substring checks."""
    chunks: List[str] = []
    for raw in paths:
        try:
            chunks.append(str(Path(raw).resolve()).replace("\\", "/").lower())
        except OSError:
            chunks.append(raw.replace("\\", "/").lower())
    return "\n".join(chunks)


def _find_marker_files(all_dirs: Set[Path]) -> List[str]:
    found: List[str] = []
    for d in all_dirs:
        try:
            if not d.is_dir():
                continue
        except OSError:
            continue
        try:
            cand = d / "ProjectSettings" / "ProjectVersion.txt"
            if cand.is_file():
                found.append(str(cand))
            pg = d / _GODOT_PROJECT
            if pg.is_file():
                found.append(str(pg))
        except OSError:
            continue
    return found


def _detect_engines(paths: List[str], file_paths: List[Path]) -> Tuple[List[str], List[Dict[str, Any]]]:
    engines: List[str] = []
    evidence: List[Dict[str, Any]] = []
    blob = _path_blob(paths)
    parts_union: Set[str] = set()
    for fp in file_paths:
        parts_union.update(_norm_parts(fp))
        try:
            parts_union.add(fp.name.lower())
        except Exception:
            pass

    has_assets = "assets" in parts_union
    has_projectsettings = "projectsettings" in parts_union
    try:
        has_unity_scene = any(fp.suffix.lower() == ".unity" for fp in file_paths)
        has_prefab = any(fp.suffix.lower() == ".prefab" for fp in file_paths)
        cs_under_assets = any(
            fp.suffix.lower() == ".cs" and "assets" in _norm_parts(fp.parent)
            for fp in file_paths
        )
    except Exception:
        has_unity_scene = has_prefab = cs_under_assets = False

    if (
        (has_assets and (has_projectsettings or has_unity_scene or has_prefab))
        or "/projectsettings/projectversion.txt" in blob
        or "\\projectsettings\\projectversion.txt" in blob
        or cs_under_assets
    ):
        engines.append("unity")
        evidence.append(
            {
                "kind": "unity_layout",
                "signals": {
                    "assets": has_assets,
                    "project_settings": has_projectsettings,
                    "unity_scene": has_unity_scene,
                    "prefab": has_prefab,
                    "csharp_under_assets": cs_under_assets,
                },
                "confidence": "high" if (has_assets and has_projectsettings) else "medium",
            }
        )

    if any(fp.name.lower() == _GODOT_PROJECT for fp in file_paths) or _GODOT_PROJECT in blob:
        engines.append("godot")
        evidence.append({"kind": "godot_project", "marker": "project.godot", "confidence": "high"})

    if any(fp.suffix.lower() == _GAMEMAKER_EXT for fp in file_paths):
        yyp = [str(fp) for fp in file_paths if fp.suffix.lower() == _GAMEMAKER_EXT]
        engines.append("gamemaker")
        evidence.append({"kind": "gamemaker", "yyp_files": yyp[:5], "confidence": "high"})

    if any(fp.suffix.lower() == _PACKET_TRACER_EXT for fp in file_paths):
        engines.append("cisco_packet_tracer")
        pkt = [str(fp) for fp in file_paths if fp.suffix.lower() == _PACKET_TRACER_EXT]
        evidence.append({"kind": "packet_tracer", "pkt_files": pkt[:5], "confidence": "high"})

    excel_files = [
        str(fp) for fp in file_paths if fp.suffix.lower() in _EXCEL_SEMANTIC_EXT
    ]
    if excel_files:
        engines.append("excel_spreadsheet")
        evidence.append(
            {
                "kind": "excel_workbook",
                "workbook_files": excel_files[:5],
                "confidence": "high",
            }
        )

    py_files = [fp for fp in file_paths if fp.suffix.lower() == ".py"]
    has_req = any(fp.name.lower() in _PYTHON_ROOT_FILES for fp in file_paths)
    if py_files and (has_req or len(py_files) >= 2):
        engines.append("python_project")
        evidence.append(
            {
                "kind": "python_project",
                "py_file_count": len(py_files),
                "has_root_marker": has_req,
                "confidence": "medium" if len(py_files) < 4 and not has_req else "high",
            }
        )

    # De-duplicate engines while keeping order
    seen_e = set()
    engines_u: List[str] = []
    for e in engines:
        if e not in seen_e:
            seen_e.add(e)
            engines_u.append(e)
    return engines_u, evidence


_SYSTEM_PATTERNS: List[Tuple[str, re.Pattern]] = [
    ("collision_system", re.compile(r"\b(OnCollision|OnTrigger|Collider|rigidbody|move_and_slide|place_meeting)\b", re.I)),
    ("physics_system", re.compile(r"\b(Rigidbody|AddForce|velocity|gravity|physics_process)\b", re.I)),
    ("ui_system", re.compile(r"\b(Canvas|UI\.|Button|Panel|Control|HBox|VBox|label|draw_text)\b", re.I)),
    ("audio_system", re.compile(r"\b(AudioSource|AudioStreamPlayer|audio_play_sound|play\()\b", re.I)),
    ("animation_system", re.compile(r"\b(Animator|AnimationPlayer|AnimatedSprite|AnimationClip)\b", re.I)),
    ("save_system", re.compile(r"\b(PlayerPrefs|save_game|load_game|json\.dump|pickle\.dump|FileAccess\.open)\b", re.I)),
    ("inventory_system", re.compile(r"\b(inventory|item_stack|hotbar|pickup_item|equip)\b", re.I)),
    ("enemy_ai", re.compile(r"\b(enemy|NavMesh|patrol|state_machine|AIController|seek|flee)\b", re.I)),
    ("input_system", re.compile(r"\b(Input\.|keyboard_check|mouse_|get_action|GetKey|GetAxis)\b", re.I)),
    ("scene_flow", re.compile(r"\b(SceneManager|load_scene|change_scene|room_goto|get_tree)\b", re.I)),
]


def _sample_code_text(file_paths: List[Path], max_total_chars: int = 120_000) -> str:
    pieces: List[str] = []
    n = 0
    for fp in sorted({str(x) for x in file_paths}):
        p = Path(fp)
        if p.suffix.lower() not in _CODE_EXT:
            continue
        try:
            if not p.is_file():
                continue
        except OSError:
            continue
        try:
            chunk = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        chunk = chunk[:25_000]
        pieces.append(chunk)
        n += len(chunk)
        if n >= max_total_chars:
            break
    return "\n".join(pieces)


def _heuristic_code_quality(code_blob: str) -> Dict[str, Any]:
    lines = [ln for ln in code_blob.splitlines() if ln.strip()]
    n_lines = len(lines)
    if n_lines == 0:
        return {"oop_score": 0, "complexity_estimate": 0, "total_source_lines": 0}

    class_hits = len(re.findall(r"\bclass\s+\w+", code_blob))
    branch_hits = len(re.findall(
        r"\b(if|for|while|switch|case|\&\&|\|\|)\b",
        code_blob,
        re.I,
    ))
    avg_len = sum(len(ln) for ln in lines[:500]) / min(500, n_lines)

    oop_score = min(100, 30 + class_hits * 12 + (1 if "interface " in code_blob else 0) * 15)
    complexity = min(100, int(branch_hits * 100 / max(n_lines, 1)))
    if avg_len > 80:
        complexity = min(100, complexity + 10)

    return {
        "oop_score": oop_score,
        "complexity_estimate": complexity,
        "total_source_lines": n_lines,
    }


def _detect_systems(code_blob: str) -> List[str]:
    out: List[str] = []
    for name, pat in _SYSTEM_PATTERNS:
        if pat.search(code_blob):
            out.append(name)
    return out


def _path_suggests_runtime_screenshot(fp: Path) -> bool:
    try:
        from app.l2_l3_corroborative_runtime import (
            classify_l2_folder_screenshot,
            path_is_engine_asset_not_runtime_capture,
        )

        if classify_l2_folder_screenshot(fp):
            return True
        if path_is_engine_asset_not_runtime_capture(fp):
            return False
    except ImportError:
        pass
    try:
        posix = fp.as_posix().lower()
    except (OSError, ValueError):
        posix = str(fp).lower()
    if any(m in posix for m in _RUNTIME_PATH_MARKERS):
        return True
    stem = fp.stem.lower()
    return any(m in stem for m in _RUNTIME_NAME_MARKERS)


def _is_runtime_log_candidate(fp: Path) -> bool:
    name = fp.name.lower()
    if name in _RUNTIME_LOG_BASENAMES:
        return True
    if fp.suffix.lower() != ".log":
        return False
    try:
        posix = fp.as_posix().lower()
    except (OSError, ValueError):
        posix = str(fp).lower()
    return "runtime" in posix or "gameplay" in posix or "capture" in posix


def _scan_runtime_log_text(text: str) -> Dict[str, Any]:
    """
    Best-effort signals from student-provided logs (Debug.Log, Player.log copy, etc.).
    Does not prove gameplay — only supports corroboration when lines exist.
    """
    sample = text[:400_000]
    t = sample.lower()
    lines = sample.splitlines()
    return {
        "line_count": len(lines),
        "char_sampled": len(sample),
        "mentions_collision": bool(
            re.search(
                r"\b(oncollisionenter|oncollisionexit|ontriggerenter|ontriggerexit|"
                r"oncollision|ontrigger|collision_enter|trigger_enter)\b",
                t,
            )
        ),
        "mentions_scene": bool(
            re.search(r"\b(loadscene|scene loaded|loaded scene|scenechange|additive scene)\b", t)
        ),
        "mentions_save": bool(re.search(r"\b(playerprefs|save game|savegame|savedata|json\.save)\b", t)),
        "mentions_ui": bool(re.search(r"\b(canvas|uibutton|button\.onclick|tmp_text|textmeshpro)\b", t)),
        "mentions_physics": bool(
            re.search(r"\b(rigidbody|addforce|velocity|gravity|physics\.raycast)\b", t)
        ),
        "mentions_audio": bool(
            re.search(r"\b(audiosource|audio\.play|playsound|sound_|music_|\.wav|\.ogg)\b", t)
        ),
        "mentions_animation": bool(
            re.search(r"\b(animator|animationclip|animator\.settrigger|spritesheet)\b", t)
        ),
        "mentions_ai": bool(
            re.search(r"\b(navmesh|nav agent|patrol|seek|flee|state machine|behavior)\b", t)
        ),
        "mentions_input": bool(
            re.search(r"\b(input\.|getkey|getbutton|getaxis|mouse button|touch)\b", t)
        ),
        "mentions_inventory": bool(
            re.search(r"\b(inventory|hotbar|pickup|loot|equip item|item stack)\b", t)
        ),
    }


def _collect_runtime_evidence(file_paths: List[Path]) -> Dict[str, Any]:
    screenshots: List[Dict[str, Any]] = []
    logs_out: List[Dict[str, Any]] = []

    for fp in sorted(file_paths, key=lambda p: str(p).lower()):
        try:
            suf = fp.suffix.lower()
        except (OSError, AttributeError):
            continue
        if suf in _RUNTIME_SCREENSHOT_EXT and _path_suggests_runtime_screenshot(fp):
            screenshots.append({"path": str(fp), "basename": fp.name})
    screenshots = sorted(screenshots, key=lambda r: r["path"].lower())[:40]

    log_candidates = [fp for fp in file_paths if _is_runtime_log_candidate(fp)]
    for fp in log_candidates[:5]:
        signals: Dict[str, Any]
        try:
            raw = fp.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            signals = {"error": "unreadable"}
        else:
            signals = _scan_runtime_log_text(raw)
        logs_out.append({"path": str(fp), "basename": fp.name, "signals": signals})

    video_files = list_submission_video_files(file_paths)
    video_block = extract_runtime_video_evidence(video_files)

    # Linkage diagnostics (presence-only; no semantics on pixels).
    if video_block.get("video_frame_count", 0) > 0:
        if not logs_out and not screenshots:
            video_block.setdefault("video_noise_flags", []).append(
                {"flag": "video_frames_extracted_without_runtime_linkage"}
            )

    merged: Dict[str, Any] = {
        "version": 1,
        "screenshot_candidates": screenshots,
        "log_files": logs_out,
        **video_block,
        "notes_ar": (
            "أدلة تشغيل مكتشفة آلياً من أسماء المسارات/الملفات فقط؛ "
            "لا تثبت صحة اللقطات أو اختصاصها بنظام معين دون ربط يدوي/لاحق."
        ),
    }
    merged.update(extract_runtime_ocr_evidence(merged))
    return merged


def _file_stats(file_paths: List[Path]) -> Dict[str, Any]:
    by_ext: Dict[str, int] = {}
    for fp in file_paths:
        ext = fp.suffix.lower() or "(no_ext)"
        by_ext[ext] = by_ext.get(ext, 0) + 1
    top = sorted(by_ext.items(), key=lambda x: -x[1])[:12]
    return {"unique_files": len(file_paths), "extensions_top": [{"ext": a, "count": b} for a, b in top]}


def build_project_profile(
    submission_paths: List[str],
    intake_relative_paths: Optional[List[str]] = None,
    *,
    lightweight: bool = False,
) -> Dict[str, Any]:
    """
    Analyze list of absolute (or relative) submission file paths.
    Returns a JSON-serializable dict for grading / logging — not raw source.
    """
    submission_paths = [p for p in submission_paths if p and p.strip()]
    file_paths: List[Path] = []
    for raw in submission_paths:
        try:
            p = Path(raw)
            if p.is_file():
                file_paths.append(p.resolve())
        except OSError:
            continue

    dirs = _collect_directories_for_paths(submission_paths)
    marker_files = _find_marker_files(dirs)
    engines, evidence = _detect_engines(submission_paths, file_paths)
    stats = _file_stats(file_paths)
    code_blob = _sample_code_text(file_paths)
    systems = _detect_systems(code_blob)
    quality = _heuristic_code_quality(code_blob)

    profile = {
        "version": 1,
        "project_types": engines if engines else ["unknown_or_document_only"],
        "engines_detected": engines,
        "systems_detected": systems,
        "code_quality": quality,
        "layout_evidence": evidence,
        "marker_files_found": marker_files[:20],
        "file_stats": stats,
        "runtime_evidence": _collect_runtime_evidence(file_paths),
        "notes_ar": (
            "ملخص آلي من بنية الملفات وأجزاء من الشيفرة فقط — لا يغني عن قراءة مستند الطالب كاملاً."
        ),
    }
    if lightweight:
        profile["systems_semantic"] = []
        profile["temporal_alignment"] = {"version": 1, "skipped_lightweight": True}
        profile["cross_modal_corroboration"] = {"version": 1, "skipped_lightweight": True}
        profile["ui_token_correlation"] = {"version": 1, "skipped_lightweight": True}
    else:
        if "unity" in engines and file_paths:
            try:
                from .unity_extractor import analyze_unity_submission

                profile["unity_semantic"] = analyze_unity_submission(file_paths)
                profile["systems_semantic"] = profile["unity_semantic"].get(
                    "system_detections", []
                )
            except Exception as exc:
                profile["unity_semantic"] = {"error": str(exc)[:300]}
                profile["systems_semantic"] = []
        else:
            profile["systems_semantic"] = []

        profile["temporal_alignment"] = build_temporal_alignment(profile)
        _rc_snap = build_runtime_corroboration(profile)
        profile["cross_modal_corroboration"] = build_cross_modal_corroboration(
            profile.get("temporal_alignment"),
            profile.get("runtime_evidence"),
            _rc_snap,
        )
        profile["ui_token_correlation"] = build_ui_token_correlation(profile)

    from .submission_intake import build_submission_intake_profile

    profile["submission_intake"] = build_submission_intake_profile(
        submission_paths,
        intake_relative_paths=intake_relative_paths,
    )

    if lightweight:
        return profile

    if "cisco_packet_tracer" in engines and file_paths:
        from .packet_tracer_extractor import (
            extract_packet_tracer_evidence,
            finalize_packet_tracer_block,
        )

        pt_block = extract_packet_tracer_evidence(file_paths)
        profile["packet_tracer_evidence"] = finalize_packet_tracer_block(pt_block)

    if "excel_spreadsheet" in engines and file_paths:
        from .excel_semantic_extractor import (
            extract_excel_semantic_evidence,
            finalize_excel_semantic_block,
        )

        xl_block = extract_excel_semantic_evidence(file_paths)
        profile["excel_semantic_evidence"] = finalize_excel_semantic_block(xl_block)

    return profile


def _slim_unity_semantic(u: Any) -> Any:
    if not u or not isinstance(u, dict):
        return None
    if "error" in u:
        return {"error": u["error"]}
    return {
        "extractor_version": u.get("extractor_version"),
        "scripts_analyzed": u.get("scripts_analyzed"),
        "monobehaviour_count": u.get("monobehaviour_count"),
        "scene_prefab_hints_count": len(u.get("scene_prefab_hints") or []),
        "limitations_ar": u.get("limitations_ar"),
    }


def format_profile_for_grading_prompt(profile: Dict[str, Any]) -> str:
    """Arabic + JSON block prepended to student payload for the LLM."""
    if not profile:
        return ""
    nfiles = profile.get("file_stats", {}).get("unique_files") or 0
    if nfiles < 1:
        return ""

    rt = profile.get("runtime_evidence") or {}
    rt_slim = {
        "screenshot_count": len(rt.get("screenshot_candidates") or []),
        "log_file_count": len(rt.get("log_files") or []),
        "video_frame_count": int(rt.get("video_frame_count") or 0),
        "video_metadata_summary": {
            "duration_seconds": (rt.get("video_metadata") or {}).get("duration_seconds"),
            "frame_count_extracted": (rt.get("video_metadata") or {}).get("frame_count_extracted"),
        },
        "video_noise_flags": rt.get("video_noise_flags") or [],
        "log_signal_summary": [
            {"basename": x.get("basename"), "signals": x.get("signals")}
            for x in (rt.get("log_files") or [])[:3]
        ],
        "ocr_evidence_count": len(
            [x for x in (rt.get("ocr_evidence_items") or []) if isinstance(x, dict)]
        ),
        "ocr_presence_flags": rt.get("ocr_presence_flags") or [],
        "ocr_noise_flags": rt.get("ocr_noise_flags") or [],
    }
    rc = build_runtime_corroboration(profile)
    rc_by = rc.get("by_system") or {}
    _strong: List[str] = []
    _weak: List[str] = []
    for _sys, _row in rc_by.items():
        if not isinstance(_row, dict):
            continue
        _st = str(_row.get("corroboration_strength") or "none")
        try:
            _w = float(_row.get("weighted_corroboration_score") or 0.0)
        except (TypeError, ValueError):
            _w = 0.0
        if _st == "medium" or _w >= 0.7:
            _strong.append(_sys)
        elif _st == "weak":
            _weak.append(_sys)
    rc_slim = {
        "by_system": rc.get("by_system"),
        "corroboration_summary": {
            "strongly_corroborated_systems": sorted(_strong),
            "weakly_corroborated_systems": sorted(_weak),
        },
        "missing_runtime_corroboration_flags": rc.get("missing_runtime_corroboration_flags"),
        "corroboration_conflicts": rc.get("corroboration_conflicts"),
        "aggregate_log_signals": rc.get("aggregate_log_signals"),
        "evidence_weights": rc.get("evidence_weights"),
    }
    ta = profile.get("temporal_alignment") or {}
    ta_slim = {
        "window_seconds": ta.get("window_seconds"),
        "temporal_alignment_strength": ta.get("temporal_alignment_strength"),
        "temporal_event_count": len(ta.get("temporal_events") or []),
        "temporal_group_count": len(ta.get("temporal_groups") or []),
        "temporal_alignment_conflicts": ta.get("temporal_alignment_conflicts") or [],
        "temporal_reasoning": (ta.get("temporal_reasoning") or {}).get("reasoning") or [],
    }
    cm = profile.get("cross_modal_corroboration") or {}
    cm_slim = {
        "version": cm.get("version"),
        "cross_modal_diversity_score": cm.get("cross_modal_diversity_score"),
        "cross_modal_window_count": len(cm.get("cross_modal_windows") or []),
        "cross_modal_noise_flags": cm.get("cross_modal_noise_flags") or [],
        "cross_modal_reasoning": (cm.get("cross_modal_reasoning") or {}).get("reasoning") or [],
        "cross_modal_windows_head": (cm.get("cross_modal_windows") or [])[:6],
    }
    ut = profile.get("ui_token_correlation") or {}
    ut_slim = {
        "version": ut.get("version"),
        "window_seconds": ut.get("window_seconds"),
        "token_group_count": len(ut.get("token_correlation_groups") or []),
        "token_noise_flags": ut.get("token_noise_flags") or [],
        "token_reasoning": (ut.get("token_reasoning") or {}).get("reasoning") or [],
        "tokens_detected": [g.get("token") for g in (ut.get("token_correlation_groups") or []) if isinstance(g, dict)],
    }
    xl = profile.get("excel_semantic_evidence") or {}
    xl_slim = None
    if isinstance(xl, dict) and xl.get("workbook_files"):
        xagg = xl.get("aggregate") or {}
        xl_slim = {
            "workbook_file_count": len(xl.get("workbook_files") or []),
            "aggregate": xagg,
            "spreadsheet_semantic_summary": xl.get("spreadsheet_semantic_summary"),
            "noise_flags": xl.get("noise_flags") or [],
            "readable_count": sum(
                1
                for r in (xl.get("extractions") or [])
                if isinstance(r, dict) and r.get("readable")
            ),
        }
    pt = profile.get("packet_tracer_evidence") or {}
    pt_slim = None
    if isinstance(pt, dict) and pt.get("pkt_files"):
        agg = pt.get("aggregate") or {}
        pt_slim = {
            "pkt_file_count": len(pt.get("pkt_files") or []),
            "aggregate": agg,
            "network_evidence_summary": pt.get("network_evidence_summary"),
            "noise_flags": pt.get("noise_flags") or [],
            "readable_count": sum(
                1 for r in (pt.get("extractions") or []) if isinstance(r, dict) and r.get("readable")
            ),
        }
    si = profile.get("submission_intake") or {}
    slim = {
        "project_types": profile.get("project_types"),
        "engines_detected": profile.get("engines_detected"),
        "systems_detected": profile.get("systems_detected"),
        "systems_semantic": profile.get("systems_semantic"),
        "unity_semantic_summary": _slim_unity_semantic(profile.get("unity_semantic")),
        "runtime_evidence_summary": rt_slim,
        "runtime_corroboration": rc_slim,
        "temporal_alignment_summary": ta_slim,
        "cross_modal_corroboration_summary": cm_slim,
        "ui_token_correlation_summary": ut_slim,
        "code_quality": profile.get("code_quality"),
        "layout_evidence": profile.get("layout_evidence"),
        "file_stats": profile.get("file_stats"),
        "packet_tracer_summary": pt_slim,
        "excel_semantic_summary": xl_slim,
        "grading_hints_ar": (
            "إن وُجد حقل systems_semantic لمشروع Unity: اعتمد ترتيب الثقة (confidence) وexecution_evidence "
            "قبل الاستدلال من systems_detected السريع؛ الثقة المنخفضة أو execution_evidence=weak تعني احتمال إيجابية كاذبة."
        ),
    }
    if isinstance(si, dict) and si.get("submission_noise_flags"):
        slim["submission_packaging_noise_note_ar"] = (
            "تنبيه تشغيلي فقط: مسارات الرفع تشمل مجلدات كاش/أدوات بناء شائعة؛ "
            "قد يزيد ذلك ضوضاء التحليل الآلي — يُفضّل تسليم ZIP مُقَطَّع (بدون Library/Temp). "
            "لا تستخدم هذا التنبيه وحده لإثبات نقص التنفيذ."
        )
    js = json.dumps(slim, ensure_ascii=False, indent=2)
    return (
        "══════════════════════════════════════════\n"
        "[PROJECT_INTELLIGENCE — ملخص بنية المشروع (تحليل آلي محلي، بدون إرسال الملفات الخام كاملة)]\n"
        "استخدم هذا كخريطة تقنية: أنواع المحرك/المشروع، أنظمة يُحتمل وجودها في الشيفرة، ومؤشرات جودة تقريبية.\n"
        "⚠️ لا تعتبر هذا بديلاً عن الأدلة المطلوبة في معايير BTEC؛ استخدمه لتوجيه البحث في نص الطالب ومرفقات الكود.\n"
        "```json\n"
        f"{js}\n"
        "```\n"
        "══════════════════════════════════════════\n"
    )
