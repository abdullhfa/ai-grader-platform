"""
Bounded L2/L3 corroborative runtime evidence — entered the chain, not authority.

Principle: runtime observation is still not criterion authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

INSTITUTIONAL_PHRASING_EN = (
    "runtime-oriented visual evidence suggests gameplay activity under limited "
    "observational conditions; criterion authority remains human-governed and was "
    "not automatically inferred from visual evidence alone"
)

INSTITUTIONAL_PHRASING_AR = (
    "أدلة بصرية/زمنية موجهة للتشغيل تشير إلى نشاط لعب محتمل ضمن شروط رصد محدودة؛ "
    "سلطة المعيار تبقى بشرية-محكومة ولم تُستنتَج تلقائياً من الأدلة البصرية وحدها"
)

AUTHORITY_CEILING = "advisory_corroborative_only"

# Folders that suggest deliberate gameplay / runtime capture evidence (BTEC Arabic layouts).
L2_FOLDER_PATH_MARKERS = (
    "runtime_evidence",
    "runtime-evidence",
    "gameplay",
    "screenshots",
    "screen_shots",
    "captures",
    "screen_capture",
    "playtest",
    "test_capture",
    "running_build",
    "btec_runtime",
    "صور تشغيل",
    "تشغيل اللعبة",
    "لقطات",
    "لقطة",
    "سكرينات",
    "سكرين",
)

# Engine asset trees — PNG here is usually art, not runtime proof.
_ENGINE_ASSET_PATH_MARKERS = (
    "/.godot/",
    "\\.godot\\",
    "/assets/",
    "/sprites/",
    "/textures/",
    "/icons/",
    "/audio/",
    "/fonts/",
    "مشروع godot",
    "/tileset",
    "/parallax",
)


def path_in_l2_evidence_folder(fp: Path) -> bool:
    try:
        parts = [p.lower() for p in fp.parts]
    except (OSError, ValueError):
        parts = [p.lower() for p in Path(str(fp)).parts]
    # Ignore calibration/corpus paths (avoid «runtime_evidence_corpus» false positive).
    if any(p in ("runtime_evidence_corpus", "calibration", "cases") for p in parts):
        tail = parts[parts.index("cases") + 2 :] if "cases" in parts else parts[-5:]
    else:
        tail = parts[-5:]
    segment_blob = "/".join(tail)
    if any(m in segment_blob for m in L2_FOLDER_PATH_MARKERS if m not in ("runtime_evidence", "runtime-evidence")):
        return True
    return any(p in ("runtime_evidence", "runtime-evidence", "btec_runtime", "captures") for p in tail)


def path_is_engine_asset_not_runtime_capture(fp: Path) -> bool:
    try:
        posix = fp.as_posix().lower()
    except (OSError, ValueError):
        posix = str(fp).lower()
    if path_in_l2_evidence_folder(fp):
        return False
    return any(m in posix for m in _ENGINE_ASSET_PATH_MARKERS)


def classify_l2_folder_screenshot(fp: Path) -> Optional[Dict[str, Any]]:
    """Return L2 corroborative metadata for a folder PNG/JPG, or None if excluded."""
    if fp.suffix.lower() not in {".png", ".jpg", ".jpeg", ".webp"}:
        return None
    if path_is_engine_asset_not_runtime_capture(fp):
        return None
    if not path_in_l2_evidence_folder(fp):
        return None
    folder_hint = ""
    for part in fp.parts:
        pl = part.lower()
        if any(m in pl for m in L2_FOLDER_PATH_MARKERS):
            folder_hint = part
            break
    return {
        "basename": fp.name,
        "path": str(fp),
        "tier": "L2",
        "source": "folder_gameplay_evidence_path",
        "folder_hint": folder_hint,
        "authority": AUTHORITY_CEILING,
        "mode": "corroborative_runtime_hint",
        "possible_signals": [
            "visual_runtime_activity_suggested",
            "gameplay_scene_plausible",
        ],
        "not_inferred": [
            "game_verified",
            "criterion_achieved",
            "functional_testing_proven",
        ],
    }


def _collect_l2_from_profile(profile: Optional[Mapping[str, Any]]) -> List[Dict[str, Any]]:
    rt = (profile or {}).get("runtime_evidence") or {}
    out: List[Dict[str, Any]] = []
    for row in rt.get("screenshot_candidates") or []:
        if not isinstance(row, dict):
            continue
        path = row.get("path") or ""
        if not path:
            continue
        meta = classify_l2_folder_screenshot(Path(path))
        if meta:
            out.append(meta)
    return out[:40]


def _collect_l3_from_inventory(inventory: Mapping[str, Any]) -> Dict[str, Any]:
    gvi = inventory.get("gameplay_video_inference") or {}
    rt_art = inventory.get("runtime_artifacts") or {}
    profile_rt = {}
    hints = (gvi.get("video_analysis") or {}).get("runtime_hints") or []
    videos = rt_art.get("gameplay_videos") or []
    return {
        "tier": "L3",
        "authority": AUTHORITY_CEILING,
        "videos_detected": len(videos),
        "videos_analyzed": int(gvi.get("videos_analyzed") or 0),
        "frames_sampled": int(gvi.get("frames_sampled") or 0),
        "runtime_hints_count": len(hints),
        "temporal_signals": [
            "movement_continuity_plausible",
            "score_or_ui_change_plausible",
            "scene_transition_plausible",
        ],
        "mode": "temporal_runtime_hint",
        "not_inferred": [
            "game_verified",
            "criterion_achieved",
            "structured_testing_proven",
        ],
        "institutional_label_en": "observed runtime activity under limited evidence conditions",
        "institutional_label_ar": "نشاط تشغيلي مُلاحَظ ضمن شروط أدلة محدودة",
    }


def _build_ambiguity_flags(
    inventory: Mapping[str, Any],
    profile: Optional[Mapping[str, Any]],
    l2_count: int,
) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []
    rt_art = inventory.get("runtime_artifacts") or {}
    testing = inventory.get("testing_evidence") or {}
    exec_block = inventory.get("executable_artifacts") or {}

    if l2_count > 0 and testing.get("status") != "verified":
        flags.append({
            "flag": "l2_visual_without_structured_testing",
            "message_ar": (
                "لقطات L2 موجودة لكن لا وثائق اختبار منظمة — "
                "visual plausibility ≠ functional testing evidence"
            ),
        })
    if rt_art.get("executables_detected") and not rt_art.get("runtime_verified"):
        flags.append({
            "flag": "executable_present_runtime_unverified",
            "message_ar": (
                "ملفات exe/apk/pck مُرصدَة دون تشغيل موثّق — "
                "presence ≠ verified implementation"
            ),
        })

    profile_rt = (profile or {}).get("runtime_evidence") or {}
    for nf in profile_rt.get("video_noise_flags") or []:
        if isinstance(nf, dict) and nf.get("flag") == "video_frames_extracted_without_runtime_linkage":
            flags.append({
                "flag": "l3_video_without_runtime_linkage",
                "message_ar": (
                    "إطارات فيديو L3 مُستخرجة دون ربط تشغيلي/logs/screenshots — "
                    "temporal hint ≠ criterion confirmation"
                ),
            })
            break

    gvi = inventory.get("gameplay_video_inference") or {}
    rt_art = inventory.get("runtime_artifacts") or {}
    has_video = bool(
        (inventory.get("media_artifacts") or {}).get("files")
        or rt_art.get("gameplay_videos")
        or profile_rt.get("video_frame_count")
    )
    frames_sampled = int(gvi.get("frames_sampled") or profile_rt.get("video_frame_count") or 0)
    if has_video and frames_sampled <= 0:
        flags.append({
            "flag": "video_detected_not_decoded",
            "message_ar": (
                "فيديو مُرصد لكن frames غير مُستخرجة — "
                "observability محدودة؛ temporal hint ≠ criterion confirmation"
            ),
        })

    if exec_block.get("status") == "detected_not_executed" and l2_count > 0:
        flags.append({
            "flag": "visual_and_executable_without_sandbox",
            "message_ar": (
                "أدلة L2/L1 معاً قد تخلق إحساس اكتمال — "
                "contradiction preserved: لا sandbox ولا human replay"
            ),
        })

    consistency = inventory.get("cross_artifact_consistency") or {}
    for amb in (consistency.get("ambiguities") or [])[:3]:
        if isinstance(amb, dict) and amb.get("message_ar"):
            flags.append({
                "flag": "cross_artifact_ambiguity",
                "message_ar": str(amb["message_ar"]),
            })

    return flags


def build_l2_l3_corroborative_runtime_evidence(
    inventory: Mapping[str, Any],
    project_profile: Optional[Mapping[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Merge folder PNG + video into corroborative runtime chain (L2/L3).
    Never upgrades criterion authority.
    """
    l2_items = _collect_l2_from_profile(project_profile)
    l3_block = _collect_l3_from_inventory(inventory)
    ambiguities = _build_ambiguity_flags(inventory, project_profile, len(l2_items))

    has_l2 = len(l2_items) > 0
    has_l3 = (l3_block.get("frames_sampled") or 0) > 0 or (l3_block.get("videos_detected") or 0) > 0

    return {
        "version": 1,
        "authority_ceiling": AUTHORITY_CEILING,
        "institutional_phrasing_en": INSTITUTIONAL_PHRASING_EN,
        "institutional_phrasing_ar": INSTITUTIONAL_PHRASING_AR,
        "l2_folder_screenshots": l2_items,
        "l2_count": len(l2_items),
        "l3_video_evidence": l3_block,
        "entered_chain": has_l2 or has_l3,
        "criterion_authority_auto_inferred": False,
        "contradictions_preserved": bool(ambiguities),
        "ambiguity_flags": ambiguities,
        "grader_instruction_ar": (
            "استخدم L2/L3 كـ corroborative hints فقط. "
            "لا تمنح C.P5/C.P6/C.M3 Achieved من visuals/video وحدها. "
            "أبقِ contradictions مرئية في الملاحظات."
        ),
    }


def format_corroborative_runtime_for_grading_prompt(block: Mapping[str, Any]) -> str:
    if not block or not block.get("entered_chain"):
        return ""
    l2 = block.get("l2_count") or 0
    l3 = block.get("l3_video_evidence") or {}
    amb = block.get("ambiguity_flags") or []
    lines = [
        "═══════════════════════════════════════════",
        "⚠️ [L2/L3 Corroborative Runtime Evidence — NOT criterion authority]",
        block.get("institutional_phrasing_en", INSTITUTIONAL_PHRASING_EN),
        f"L2 folder screenshots ingested: {l2}",
        f"L3 video temporal hints: frames={l3.get('frames_sampled', 0)}, "
        f"videos={l3.get('videos_detected', 0)}",
        "→ runtime observation is still not criterion authority",
        "→ do NOT auto-award C.P5/C.P6/C.M3 from visual/video hints alone",
    ]
    if amb:
        lines.append("Contradictions / ambiguity (must remain visible):")
        for a in amb[:5]:
            if isinstance(a, dict) and a.get("message_ar"):
                lines.append(f"  - {a['message_ar']}")
    lines.append("═══════════════════════════════════════════")
    return "\n".join(lines) + "\n\n"
