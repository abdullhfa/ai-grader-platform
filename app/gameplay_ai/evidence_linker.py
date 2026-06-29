"""Evidence correlation — links criteria hints to multi-source detections."""
from __future__ import annotations

from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult


CRITERION_HINTS = {
    "game_launch": ["motion_detector", "ui_detector", "scene_change"],
    "gameplay_loop": ["motion_detector", "freeze_detector", "progression_detector"],
    "lose_health": ["score_detector", "death_detector", "text_ocr"],
    "win_lose_state": ["win_detector", "lose_detector"],
    "testing_evidence": ["fps_monitor", "input_trace"],
}


def correlate_evidence(detections: List[DetectionResult]) -> List[Dict[str, Any]]:
    by_detector = {d.detector: d for d in detections}
    links: List[Dict[str, Any]] = []

    for criterion, detectors in CRITERION_HINTS.items():
        matched = []
        for name in detectors:
            det = by_detector.get(name)
            if not det:
                continue
            matched.append(
                {
                    "detector": det.detector,
                    "label": det.label,
                    "confidence": det.confidence,
                }
            )
        if not matched:
            continue
        avg_conf = sum(m["confidence"] for m in matched) / len(matched)
        links.append(
            {
                "criterion_hint": criterion,
                "supporting_detectors": matched,
                "aggregate_confidence": round(avg_conf, 3),
                "corroboration_strength": (
                    "strong" if avg_conf >= 0.75 and len(matched) >= 2 else
                    "moderate" if avg_conf >= 0.55 else "weak"
                ),
            }
        )
    return links
