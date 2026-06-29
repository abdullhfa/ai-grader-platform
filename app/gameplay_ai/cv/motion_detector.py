"""Motion detection across frame sequences."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult


def detect_motion(paths: List[Path], *, motion_threshold: float = 0.015) -> DetectionResult:
    from app.gameplay_ai.cv.freeze_detector import _pair_deltas

    deltas = _pair_deltas(paths)
    if not deltas:
        return DetectionResult(
            detector="motion_detector",
            label="unknown",
            confidence=0.2,
            evidence={"frame_count": len(paths)},
        )

    avg = sum(deltas) / len(deltas)
    max_delta = max(deltas)
    movement = avg >= motion_threshold or max_delta >= motion_threshold * 2
    confidence = min(0.92, 0.55 + avg * 12.0)
    return DetectionResult(
        detector="motion_detector",
        label="movement_detected" if movement else "static_scene",
        confidence=confidence,
        evidence={
            "avg_delta": round(avg, 5),
            "max_delta": round(max_delta, 5),
            "motion_threshold": motion_threshold,
        },
        method="temporal_delta",
    )
