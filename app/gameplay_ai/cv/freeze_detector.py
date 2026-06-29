"""Temporal freeze detection — deterministic, high-value for BTEC."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult


def _pair_deltas(paths: List[Path]) -> List[float]:
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return []

    deltas: List[float] = []
    if len(paths) < 2:
        return deltas
    prev = Image.open(paths[0]).convert("L").resize((160, 90))
    for fp in paths[1:]:
        curr = Image.open(fp).convert("L").resize((160, 90))
        diff = ImageChops.difference(prev, curr)
        pixels = list(diff.getdata())
        mean_delta = sum(pixels) / (160 * 90 * 255)
        deltas.append(mean_delta)
        prev = curr
    return deltas


def detect_freeze(paths: List[Path], *, threshold: float = 0.008) -> DetectionResult:
    deltas = _pair_deltas(paths)
    if len(deltas) < 2:
        return DetectionResult(
            detector="freeze_detector",
            label="insufficient_frames",
            confidence=0.2,
            evidence={"frame_count": len(paths)},
        )

    avg_delta = sum(deltas) / len(deltas)
    frozen = avg_delta < threshold
    confidence = 0.88 if frozen else 0.72
    return DetectionResult(
        detector="freeze_detector",
        label="freeze_detected" if frozen else "motion_present",
        confidence=confidence,
        evidence={
            "avg_frame_delta": round(avg_delta, 5),
            "threshold": threshold,
            "pair_deltas": [round(d, 5) for d in deltas[:12]],
            "frame_count": len(paths),
        },
        method="temporal_pixel_delta",
    )


def detect_freeze_report(paths: List[Path]) -> Dict[str, Any]:
    result = detect_freeze(paths)
    return result.to_dict()
