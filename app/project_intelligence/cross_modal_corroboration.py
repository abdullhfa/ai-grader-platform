"""
Cross-modal observation: modality overlap within temporal windows only.

Uses temporal_alignment groups + runtime_evidence presence + runtime_corroboration
metadata. Diagnostic / calibration only — does not affect achieved or final grades.
"""
from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional, Set

CROSS_MODAL_VERSION = "1.0"
# runtime_log | runtime_screenshot | video_frame | ocr_text
EXPECTED_RUNTIME_MODALITIES = 4


def _event_tags_to_modalities(events: List[Any]) -> Set[str]:
    mods: Set[str] = set()
    for ev in events or []:
        tag = str(ev)
        if tag == "video_frame":
            mods.add("video_frame")
        elif tag == "ocr_text":
            mods.add("ocr_text")
        elif tag == "runtime_screenshot":
            mods.add("runtime_screenshot")
        elif tag.startswith("runtime_log"):
            mods.add("runtime_log")
    return mods


def _overlap_strength(modality_count: int) -> str:
    if modality_count <= 1:
        return "weak"
    if modality_count == 2:
        return "medium"
    return "strong"


def _build_cross_modal_windows(
    temporal_groups: List[Mapping[str, Any]],
) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    for g in temporal_groups or []:
        if not isinstance(g, dict):
            continue
        events = g.get("events") or []
        mods = _event_tags_to_modalities(list(events))
        sorted_mods = sorted(mods)
        out.append(
            {
                "window_start": g.get("window_start"),
                "window_end": g.get("window_end"),
                "modalities_present": sorted_mods,
                "overlap_strength": _overlap_strength(len(sorted_mods)),
            }
        )
    return out


def _build_reasoning(windows: List[Dict[str, Any]]) -> Dict[str, List[str]]:
    reasons: Set[str] = set()
    for w in windows:
        m = set(w.get("modalities_present") or [])
        if "ocr_text" in m and "runtime_log" in m:
            reasons.add("ocr_text_detected_with_runtime_log")
        if "video_frame" in m and len(m) > 1:
            reasons.add("video_frame_present_in_same_temporal_window")
        if "runtime_screenshot" in m and "video_frame" in m:
            reasons.add("runtime_screenshot_and_video_frame_temporal_overlap")
        if "runtime_log" in m and "video_frame" in m:
            reasons.add("runtime_log_and_video_frame_temporal_overlap")
        if "runtime_log" in m and "runtime_screenshot" in m:
            reasons.add("runtime_log_and_screenshot_temporal_overlap")
        if "ocr_text" in m and "video_frame" in m:
            reasons.add("ocr_text_and_video_frame_temporal_overlap")
    return {"reasoning": sorted(reasons)}


def _ocr_globally_present(runtime_evidence: Optional[Mapping[str, Any]], windows: List[Dict[str, Any]]) -> bool:
    if any("ocr_text" in set(w.get("modalities_present") or []) for w in windows):
        return True
    if not runtime_evidence or not isinstance(runtime_evidence, dict):
        return False
    items = runtime_evidence.get("ocr_evidence_items") or []
    return bool(items) and any(isinstance(x, dict) for x in items)


def _build_noise_flags(
    windows: List[Dict[str, Any]],
    union_modalities: Set[str],
    runtime_evidence: Optional[Mapping[str, Any]],
) -> List[Dict[str, str]]:
    flags: List[Dict[str, str]] = []

    has_ocr = _ocr_globally_present(runtime_evidence, windows)
    ocr_with_log_window = any(
        {"ocr_text", "runtime_log"} <= set(w.get("modalities_present") or [])
        for w in windows
    )
    if has_ocr and not ocr_with_log_window:
        flags.append({"flag": "ocr_present_without_runtime_log", "detail": "no_shared_window"})

    vf_count = 0
    if runtime_evidence and isinstance(runtime_evidence, dict):
        try:
            vf_count = max(0, int(runtime_evidence.get("video_frame_count") or 0))
        except (TypeError, ValueError):
            vf_count = 0

    vf_windows = [w for w in windows if "video_frame" in set(w.get("modalities_present") or [])]
    if vf_count > 0:
        if not vf_windows:
            flags.append(
                {"flag": "video_frames_present_without_temporal_overlap", "detail": "no_video_windows"}
            )
        elif all(
            w.get("overlap_strength") == "weak"
            and set(w.get("modalities_present") or []) == {"video_frame"}
            for w in vf_windows
        ):
            flags.append(
                {
                    "flag": "video_frames_present_without_temporal_overlap",
                    "detail": "video_only_windows",
                }
            )

    if (
        len(union_modalities) >= 3
        and windows
        and all(w.get("overlap_strength") == "weak" for w in windows)
    ):
        flags.append(
            {
                "flag": "multimodal_presence_split_across_windows",
                "detail": str(len(union_modalities)),
            }
        )

    return flags


def _diversity_score(union_modalities: Set[str]) -> float:
    return round(len(union_modalities) / float(EXPECTED_RUNTIME_MODALITIES), 4)


def _corroboration_reference(runtime_corroboration: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    if not runtime_corroboration or not isinstance(runtime_corroboration, dict):
        return {}
    ref: Dict[str, Any] = {"engine_version": runtime_corroboration.get("engine_version")}
    conflicts = runtime_corroboration.get("corroboration_conflicts") or []
    if isinstance(conflicts, list) and conflicts:
        ref["corroboration_conflict_count"] = len(conflicts)
    return ref


def build_cross_modal_corroboration(
    temporal_alignment: Optional[Mapping[str, Any]],
    runtime_evidence: Optional[Mapping[str, Any]],
    runtime_corroboration: Optional[Mapping[str, Any]],
) -> Dict[str, Any]:
    """
    Observe modality overlap per temporal window. Inputs are profile slices only.
    """
    if not temporal_alignment or not isinstance(temporal_alignment, dict):
        return {
            "version": CROSS_MODAL_VERSION,
            "cross_modal_windows": [],
            "cross_modal_reasoning": {"reasoning": []},
            "cross_modal_noise_flags": [],
            "cross_modal_diversity_score": 0.0,
            "runtime_corroboration_reference": _corroboration_reference(runtime_corroboration),
        }

    groups = temporal_alignment.get("temporal_groups") or []
    if not isinstance(groups, list):
        groups = []

    cross_modal_windows = _build_cross_modal_windows(groups)
    union: Set[str] = set()
    for w in cross_modal_windows:
        union.update(w.get("modalities_present") or [])

    reasoning = _build_reasoning(cross_modal_windows)
    noise = _build_noise_flags(cross_modal_windows, union, runtime_evidence)

    return {
        "version": CROSS_MODAL_VERSION,
        "cross_modal_windows": cross_modal_windows,
        "cross_modal_reasoning": reasoning,
        "cross_modal_noise_flags": noise,
        "cross_modal_diversity_score": _diversity_score(union),
        "runtime_corroboration_reference": _corroboration_reference(runtime_corroboration),
    }
