"""
L3 — Governed gameplay video observation hints (advisory only).

Not «video understanding AI» — deterministic frame sampling + temporal signals +
cross-artifact corroboration. Video increases plausibility, NOT authority.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from app.project_intelligence.video_runtime_extractor import (
    extract_runtime_video_evidence,
    list_submission_video_files,
)

# Hint → source code filename tokens for corroboration
_HINT_CORROBORATION_TOKENS: Dict[str, Tuple[str, ...]] = {
    "score_visible": ("score", "points", "hud", "ui"),
    "player_movement": ("player", "character", "movement", "controller", "body"),
    "gameplay_loop": ("game", "main", "loop", "state"),
    "menu_navigation": ("menu", "start", "pause", "title", "button"),
    "level_transition": ("level", "scene", "stage", "world"),
    "hud_persistence": ("hud", "ui", "overlay", "canvas"),
}

_FORBIDDEN_VIDEO_CLAIMS = frozenset({
    "gameplay verified",
    "game completed",
    "mechanic confirmed",
    "runtime validated",
    "game verified",
})


def _load_frame_gray(frame_path: Path) -> Optional[Any]:
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except ImportError:
        return None
    img = cv2.imread(str(frame_path), cv2.IMREAD_GRAYSCALE)
    if img is None:
        return None
    return img


def _frame_histogram(img: Any) -> Any:
    import cv2  # type: ignore
    return cv2.calcHist([img], [0], None, [32], [0, 256])


def _hist_distance(h1: Any, h2: Any) -> float:
    import cv2  # type: ignore
    return float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))


def _motion_energy(prev: Any, curr: Any) -> float:
    import numpy as np  # type: ignore
    diff = np.abs(curr.astype("float32") - prev.astype("float32"))
    return float(diff.mean())


def _band_variance(img: Any, band: str) -> float:
    import numpy as np  # type: ignore
    h = img.shape[0]
    if band == "top":
        region = img[: max(1, h // 7), :]
    else:
        region = img[max(0, h - h // 7) :, :]
    return float(np.var(region))


def _analyze_sampled_frames(
    frame_items: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Deterministic temporal signals from sampled keyframes."""
    paths: List[Tuple[float, Path]] = []
    for item in frame_items:
        fp = Path(str(item.get("frame_path") or ""))
        if fp.is_file():
            ts = float(item.get("timestamp_seconds") or 0)
            paths.append((ts, fp))
    paths.sort(key=lambda x: x[0])

    if len(paths) < 2:
        return {
            "frame_count_analyzed": len(paths),
            "scene_changes": [],
            "temporal_signals": {},
            "runtime_hints": [],
            "analysis_error": "insufficient_frames" if len(paths) < 2 else None,
        }

    scene_changes: List[Dict[str, Any]] = []
    motion_scores: List[float] = []
    top_band_vars: List[float] = []
    bottom_band_vars: List[float] = []
    top_band_hist_dists: List[float] = []
    frame_paths_out: List[str] = []
    prev_gray = None
    prev_hist = None
    prev_top_hist = None

    for ts, fp in paths:
        gray = _load_frame_gray(fp)
        if gray is None:
            continue
        frame_paths_out.append(str(fp))
        hist = _frame_histogram(gray)
        import cv2  # type: ignore
        top_region = gray[: max(1, gray.shape[0] // 7), :]
        top_hist = cv2.calcHist([top_region], [0], None, [16], [0, 256])
        top_band_vars.append(_band_variance(gray, "top"))
        bottom_band_vars.append(_band_variance(gray, "bottom"))

        if prev_top_hist is not None:
            top_band_hist_dists.append(_hist_distance(prev_top_hist, top_hist))

        if prev_gray is not None and prev_hist is not None:
            dist = _hist_distance(prev_hist, hist)
            motion = _motion_energy(prev_gray, gray)
            motion_scores.append(motion)
            if dist > 0.35:
                scene_changes.append({
                    "timestamp_seconds": ts,
                    "histogram_distance": round(dist, 4),
                    "signal": "possible_scene_change",
                })

        prev_gray = gray
        prev_hist = hist
        prev_top_hist = top_hist
    hints: List[Dict[str, Any]] = []

    if motion_scores:
        avg_motion = sum(motion_scores) / len(motion_scores)
        temporal["average_motion_energy"] = round(avg_motion, 4)
        if avg_motion > 4.0:
            temporal["player_displacement_hint"] = True
            hints.append(_hint("player_movement", "sprite_displacement_across_frames", "low"))

    if len(scene_changes) >= 1:
        temporal["scene_transition_count"] = len(scene_changes)
        hints.append(_hint("level_transition", "histogram_scene_change", "low"))

    if top_band_vars and bottom_band_vars and len(top_band_vars) >= 3:
        top_stable = max(top_band_vars) - min(top_band_vars) < 800
        bottom_stable = max(bottom_band_vars) - min(bottom_band_vars) < 800
        top_hist_stable = (
            bool(top_band_hist_dists)
            and max(top_band_hist_dists) < 0.08
        )
        if top_stable or bottom_stable:
            temporal["hud_band_stability"] = {
                "top_stable": top_stable,
                "bottom_stable": bottom_stable,
            }
            temporal["top_band_histogram_stable"] = top_hist_stable
            if top_hist_stable and motion_scores and max(motion_scores) > 2.5:
                temporal["score_region_static_across_frames"] = True
            hints.append(_hint("hud_persistence", "ui_band_low_variance_across_frames", "low"))
            hints.append(_hint("score_visible", "possible_hud_region_persistent", "low"))

    if len(scene_changes) == 0 and motion_scores and max(motion_scores) > 2.0:
        temporal["continuous_gameplay_loop_hint"] = True
        hints.append(_hint("gameplay_loop", "repeated_interaction_without_scene_cut", "low"))

    if len(paths) >= 4 and len(scene_changes) >= 2:
        hints.append(_hint("menu_navigation", "multiple_scene_transitions", "low"))

    return {
        "frame_count_analyzed": len(paths),
        "frame_paths": frame_paths_out,
        "scene_changes": scene_changes[:8],
        "temporal_signals": temporal,
        "runtime_hints": _dedupe_hints(hints),
        "analysis_error": None,
    }


def _hint(hint_type: str, detail: str, confidence: str) -> Dict[str, Any]:
    return {
        "hint_type": hint_type,
        "detail": detail,
        "confidence": confidence,
        "claim_mode": "possible_runtime_evidence",
        "authority": "advisory_video_inference",
    }


def _dedupe_hints(hints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    seen: Set[str] = set()
    out: List[Dict[str, Any]] = []
    for h in hints:
        key = h.get("hint_type") or ""
        if key in seen:
            continue
        seen.add(key)
        out.append(h)
    return out


def _corroborate_hints(
    hints: List[Dict[str, Any]],
    *,
    source_files: Optional[List[Dict[str, Any]]] = None,
    screenshot_intel_items: Optional[List[Dict[str, Any]]] = None,
) -> List[Dict[str, Any]]:
    source_names = " ".join(
        str(f.get("name", "")).lower() for f in (source_files or [])
    )
    shot_evidence: Set[str] = set()
    for item in screenshot_intel_items or []:
        for ev in item.get("possible_evidence") or []:
            shot_evidence.add(str(ev).lower())

    enriched: List[Dict[str, Any]] = []
    for h in hints:
        hint_type = str(h.get("hint_type") or "")
        tokens = _HINT_CORROBORATION_TOKENS.get(hint_type, ())
        corroborated_by: List[str] = []
        for tok in tokens:
            if tok in source_names:
                for f in source_files or []:
                    name = str(f.get("name", ""))
                    if tok in name.lower():
                        corroborated_by.append(name)
        # Screenshot intel overlap
        for ev in shot_evidence:
            if hint_type.replace("_", "") in ev.replace("_", "") or ev in hint_type:
                corroborated_by.append(f"screenshot_intel:{ev}")

        corroborated_by = list(dict.fromkeys(corroborated_by))[:5]
        authority_strength = "weak"
        if len(corroborated_by) >= 2:
            authority_strength = "medium"
        elif len(corroborated_by) == 1:
            authority_strength = "weak_corroborated"

        enriched.append({
            **h,
            "corroborated_by": corroborated_by,
            "corroboration_present": bool(corroborated_by),
            "hint_authority": authority_strength,
            "note_ar": (
                "سلطة hint ضعيفة — بدون corroboration"
                if not corroborated_by
                else "corroboration جزئي — لا يزال advisory"
            ),
        })
    return enriched


def build_temporal_evidence_authority(
    video_analysis: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Temporal evidence authority — distinct from static screenshot authority.
    Sequence / continuity / motion — NOT automatically higher authority.
    """
    hints = video_analysis.get("runtime_hints") or []
    signals = video_analysis.get("temporal_signals") or {}
    corroborated = sum(1 for h in hints if h.get("corroboration_present"))
    total = len(hints)

    if total == 0:
        level = 0
        label = "no_temporal_signals"
    elif corroborated == 0:
        level = 1
        label = "temporal_hints_uncorroborated"
    elif corroborated < total:
        level = 2
        label = "partial_temporal_corroboration"
    else:
        level = 2
        label = "temporal_corroboration_advisory"

    return {
        "version": 1,
        "temporal_authority_level": level,
        "label_en": label,
        "label_ar": {
            "no_temporal_signals": "لا إشارات temporal",
            "temporal_hints_uncorroborated": "hints زمنية — بدون corroboration",
            "partial_temporal_corroboration": "corroboration زمني جزئي",
            "temporal_corroboration_advisory": "corroboration زمني — استشاري فقط",
        }.get(label, label),
        "max_claim_authority": "advisory_video_inference",
        "forbidden_claims": sorted(_FORBIDDEN_VIDEO_CLAIMS),
        "allowed_claims_en": [
            "gameplay_activity_inferred",
            "mechanic_visually_suggested",
            "runtime_hints_observed",
        ],
        "allowed_claims_ar": [
            "نشاط لعب مُستدَل — ليس verified",
            "mechanic مقترح بصرياً — advisory",
            "runtime hints مرصودة — بدون validation",
        ],
        "temporal_signals_present": bool(signals),
        "scene_change_count": len(video_analysis.get("scene_changes") or []),
        "note_ar": (
            "سلطة temporal ≠ سلطة runtime — الفيديو يرفع plausibility لا verification."
        ),
    }


def analyze_gameplay_video_hints(
    file_paths: List[Path],
    *,
    source_files: Optional[List[Dict[str, Any]]] = None,
    screenshot_intel_items: Optional[List[Dict[str, Any]]] = None,
    existing_video_evidence: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Main L3 entry — governed gameplay observation hints from submission videos.
    """
    videos = list_submission_video_files(file_paths)
    if not videos:
        return {
            "version": 1,
            "mode": "advisory_only",
            "videos_analyzed": 0,
            "runtime_verified": False,
            "video_analysis": {},
            "temporal_evidence_authority": build_temporal_evidence_authority({}),
            "note_ar": "لا فيديو gameplay في التسليم.",
        }

    if existing_video_evidence and existing_video_evidence.get("video_evidence_items"):
        video_block = existing_video_evidence
    else:
        video_block = extract_runtime_video_evidence(videos)

    frame_items = video_block.get("video_evidence_items") or []
    analysis = _analyze_sampled_frames(frame_items)
    analysis["runtime_hints"] = _corroborate_hints(
        analysis.get("runtime_hints") or [],
        source_files=source_files,
        screenshot_intel_items=screenshot_intel_items,
    )

    temporal_auth = build_temporal_evidence_authority(analysis)

    return {
        "version": 1,
        "mode": "governed_gameplay_observation_hints",
        "runtime_verified": False,
        "videos_analyzed": len(videos),
        "video_sources": [v.name for v in videos[:5]],
        "frames_sampled": video_block.get("video_frame_count") or 0,
        "video_extraction_errors": video_block.get("video_extraction_errors") or [],
        "video_evidence_items": video_block.get("video_evidence_items") or [],
        "video_analysis": analysis,
        "temporal_evidence_authority": temporal_auth,
        "language_contract_ar": (
            "استخدم: gameplay activity inferred / mechanic visually suggested — "
            "لا: gameplay verified / game completed."
        ),
        "note_ar": (
            "تحليل فيديو L3 — frame sampling + temporal signals فقط؛ "
            "لا vision narrative ولا runtime authority."
        ),
    }


def format_gameplay_video_inference_for_grading(block: Dict[str, Any]) -> str:
    if not block or block.get("videos_analyzed", 0) == 0:
        return ""

    lines = [
        "═══════════════════════════════════════════════════════════",
        "[L3 Gameplay Video Inference | advisory — plausibility ≠ authority]",
        "═══════════════════════════════════════════════════════════",
    ]
    lines.append(
        f"• فيديو: {block.get('videos_analyzed')} — frames: {block.get('frames_sampled')}"
    )
    ta = block.get("temporal_evidence_authority") or {}
    lines.append(
        f"• temporal_evidence_authority: L{ta.get('temporal_authority_level')} — "
        f"{ta.get('label_ar', '')}"
    )

    analysis = block.get("video_analysis") or {}
    for sig, val in (analysis.get("temporal_signals") or {}).items():
        lines.append(f"• temporal signal: {sig} = {val}")

    for h in (analysis.get("runtime_hints") or [])[:8]:
        corr = ", ".join(h.get("corroborated_by") or []) or "none"
        lines.append(
            f"• hint [{h.get('hint_type')}]: {h.get('detail')} — "
            f"confidence={h.get('confidence')} — corroborated_by={corr}"
        )

    lines.append(f"• {block.get('language_contract_ar', '')}")
    lines.append(
        "  ⛔ الفيديو يرفع plausibility — **لا** يرفع criterion authority."
    )
    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)
