"""
Temporal Consistency Governance — cross-temporal contradiction signals.

Emits temporal_consistency_signal for claim_authority_flags — NOT direct grading.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional, Set

_PLATFORMER_HINTS = frozenset({"player_movement", "level_transition", "platformer_mechanics"})
_PUZZLE_CODE_TOKENS = ("puzzle", "match", "grid", "tile", "sudoku", "logic")
_PLATFORMER_CODE_TOKENS = ("platform", "jump", "rigidbody", "characterbody", "velocity")


def _load_gray_hist_distance(path_a: Path, path_b: Path) -> Optional[float]:
    try:
        import cv2  # type: ignore
    except ImportError:
        return None
    a = cv2.imread(str(path_a), cv2.IMREAD_GRAYSCALE)
    b = cv2.imread(str(path_b), cv2.IMREAD_GRAYSCALE)
    if a is None or b is None:
        return None
    h1 = cv2.calcHist([a], [0], None, [32], [0, 256])
    h2 = cv2.calcHist([b], [0], None, [32], [0, 256])
    return float(cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA))


def _code_genre_signals(source_files: Optional[List[Dict[str, Any]]]) -> Set[str]:
    blob = " ".join(str(f.get("name", "")).lower() for f in (source_files or []))
    genres: Set[str] = set()
    if any(t in blob for t in _PUZZLE_CODE_TOKENS):
        genres.add("puzzle")
    if any(t in blob for t in _PLATFORMER_CODE_TOKENS):
        genres.add("platformer")
    return genres


def _screenshot_paths(inventory: Dict[str, Any]) -> List[Path]:
    paths: List[Path] = []
    rt = inventory.get("runtime_artifacts") or {}
    for item in rt.get("screenshot_candidates") or []:
        p = Path(str(item.get("path", "")))
        if p.is_file():
            paths.append(p)
    return paths[:8]


def _video_frame_paths(inventory: Dict[str, Any]) -> List[Path]:
    gvi = inventory.get("gameplay_video_inference") or {}
    analysis = gvi.get("video_analysis") or {}
    items = analysis.get("frame_paths") or []
    out: List[Path] = []
    for raw in items:
        p = Path(str(raw))
        if p.is_file():
            out.append(p)
    if not out:
        for item in gvi.get("video_evidence_items") or []:
            p = Path(str(item.get("frame_path", "")))
            if p.is_file():
                out.append(p)
    return out[:12]


def build_temporal_consistency_report(
    inventory: Dict[str, Any],
    *,
    project_profile: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """
    Cross-temporal contradiction handling — advisory governance signals only.
    """
    signals: List[Dict[str, Any]] = []
    gvi = inventory.get("gameplay_video_inference") or {}
    analysis = gvi.get("video_analysis") or {}
    temporal = analysis.get("temporal_signals") or {}
    hints = analysis.get("runtime_hints") or []
    hint_types = {str(h.get("hint_type")) for h in hints}

    # ── HUD stable but score region static (possible fake loop) ──
    hud = temporal.get("hud_band_stability") or {}
    score_static = temporal.get("score_region_static_across_frames")
    if score_static is None:
        # infer from exported metric if present
        score_static = temporal.get("top_band_histogram_stable") and temporal.get("average_motion_energy", 0) > 3
    if (hud.get("top_stable") or hud.get("bottom_stable")) and score_static:
        signals.append({
            "code": "hud_stable_score_unchanged",
            "severity": "medium",
            "message_ar": (
                "HUD يبدو ثابتاً عبر frames لكن منطقة score/HUD لا تُظهر تغيّراً — "
                "possible fake loop / weak runtime confidence."
            ),
            "resolution": "downgrade_temporal_authority",
            "affects": "temporal_evidence_authority",
        })

    # ── Motion without gameplay transitions ──
    avg_motion = float(temporal.get("average_motion_energy") or 0)
    scene_count = int(temporal.get("scene_transition_count") or len(analysis.get("scene_changes") or []))
    if avg_motion > 4.0 and scene_count == 0:
        signals.append({
            "code": "motion_without_gameplay_transitions",
            "severity": "low",
            "message_ar": (
                "motion energy مرتفع بدون scene transitions — "
                "weak runtime confidence (قد يكون loop أو idle animation)."
            ),
            "resolution": "advisory_only",
            "affects": "hint_authority",
        })

    # ── Video vs standalone screenshots mismatch ──
    vframes = _video_frame_paths(inventory)
    shots = _screenshot_paths(inventory)
    if vframes and shots:
        vf = vframes[len(vframes) // 2]
        mismatches = 0
        comparisons = 0
        for sp in shots[:4]:
            dist = _load_gray_hist_distance(vf, sp)
            if dist is None:
                continue
            comparisons += 1
            if dist > 0.45:
                mismatches += 1
        if comparisons >= 2 and mismatches >= comparisons:
            signals.append({
                "code": "video_screenshot_visual_mismatch",
                "severity": "medium",
                "message_ar": (
                    "frames الفيديو لا تطابق لقطات المجلد بصرياً — artifact inconsistency."
                ),
                "resolution": "require_corroboration",
                "affects": "cross_artifact_consistency",
            })

    # ── Modality divergence: video hints platformer, code suggests puzzle ──
    source_files = (inventory.get("source_code") or {}).get("files") or []
    code_genres = _code_genre_signals(source_files)
    video_platformer = bool(hint_types & _PLATFORMER_HINTS)
    shot_intel = inventory.get("screenshot_intelligence") or {}
    shot_evidence: Set[str] = set()
    for item in shot_intel.get("items") or []:
        for ev in item.get("possible_evidence") or []:
            shot_evidence.add(str(ev).lower())

    if video_platformer and "puzzle" in code_genres and "platformer" not in code_genres:
        signals.append({
            "code": "modality_divergence_video_platformer_code_puzzle",
            "severity": "high",
            "message_ar": (
                "فيديو/hints توحي platformer لكن الكود يشير puzzle — modality divergence."
            ),
            "resolution": "advisory_hold_corroboration",
            "affects": "authority_mapping",
        })
    elif video_platformer and "platformer_mechanics" not in shot_evidence and not code_genres:
        signals.append({
            "code": "video_hints_without_static_corroboration",
            "severity": "low",
            "message_ar": (
                "temporal hints (movement/levels) بدون corroboration من screenshots أو code."
            ),
            "resolution": "weak_temporal_authority",
            "affects": "temporal_evidence_authority",
        })

    # ── Cross-artifact consistency amplification ──
    cross = inventory.get("cross_artifact_consistency") or {}
    if cross.get("has_unresolved_high_severity") and gvi.get("videos_analyzed"):
        signals.append({
            "code": "temporal_plus_cross_artifact_high_ambiguity",
            "severity": "high",
            "message_ar": (
                "تعارض cross-artifact عالي + evidence temporal — "
                "لا ترفع authority فوق advisory."
            ),
            "resolution": "block_authority_escalation",
            "affects": "runtime_evidence_level",
        })

    return {
        "version": 1,
        "mode": "temporal_consistency_governance",
        "signal_count": len(signals),
        "has_contradictions": bool(signals),
        "temporal_consistency_signals": signals,
        "note_ar": (
            "إشارات temporal consistency تدخل claim_authority_flags — "
            "**لا** تغيّر الدرجة مباشرة."
        ),
    }


def format_temporal_consistency_for_grading(report: Dict[str, Any]) -> str:
    signals = report.get("temporal_consistency_signals") or []
    if not signals:
        return ""
    lines = [
        "═══════════════════════════════════════════════════════════",
        "[Temporal Consistency Governance | contradiction signals]",
        "═══════════════════════════════════════════════════════════",
    ]
    for sig in signals[:6]:
        lines.append(
            f"• [{sig.get('severity')}] {sig.get('code')}: {sig.get('message_ar', '')}"
        )
    lines.append(
        "• contradictions تُخفّض temporal authority — **لا** Not Achieved تلقائي."
    )
    lines.append("═══════════════════════════════════════════════════════════\n")
    return "\n".join(lines)
