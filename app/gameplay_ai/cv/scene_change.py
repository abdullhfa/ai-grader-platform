"""Scene change detection — histogram + optional perceptual hash."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent


def _histogram(path: Path) -> List[float]:
    try:
        from PIL import Image
    except ImportError:
        return []
    img = Image.open(path).convert("L").resize((64, 64))
    hist = img.histogram()[:256]
    total = sum(hist) or 1
    return [h / total for h in hist]


def _hist_distance(a: List[float], b: List[float]) -> float:
    if not a or not b:
        return 0.0
    n = min(len(a), len(b))
    return sum(abs(a[i] - b[i]) for i in range(n)) / n


def detect_scene_changes(
    paths: List[Path],
    timestamps: List[float],
    *,
    change_threshold: float = 0.12,
) -> Tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    if len(paths) < 2:
        return DetectionResult(
            detector="scene_change",
            label="insufficient_frames",
            confidence=0.2,
            evidence={},
        ), events

    changes: List[Dict[str, Any]] = []
    prev_hist = _histogram(paths[0])
    for index in range(1, len(paths)):
        curr_hist = _histogram(paths[index])
        dist = _hist_distance(prev_hist, curr_hist)
        ts = timestamps[index] if index < len(timestamps) else float(index)
        if dist >= change_threshold:
            changes.append({"index": index, "timestamp": ts, "distance": round(dist, 4)})
            events.append(
                GameplayEvent(
                    timestamp=ts,
                    type="scene_change",
                    confidence=min(0.95, 0.5 + dist),
                    payload={"histogram_distance": round(dist, 4), "frame_index": index},
                )
            )
        prev_hist = curr_hist

    label = "scene_changes_detected" if changes else "stable_scene"
    confidence = 0.85 if changes else 0.7
    return DetectionResult(
        detector="scene_change",
        label=label,
        confidence=confidence,
        evidence={"changes": changes, "change_count": len(changes)},
        method="histogram_diff",
    ), events
