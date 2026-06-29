"""Frame-level metrics from temporal sequence."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.gameplay_ai.cv.freeze_detector import _pair_deltas


def compute_frame_metrics(paths: List[Path], timestamps: List[float]) -> Dict[str, Any]:
    deltas = _pair_deltas(paths)
    if not deltas:
        return {"frame_count": len(paths), "metrics_available": False}

    intervals: List[float] = []
    for i in range(1, len(timestamps)):
        gap = timestamps[i] - timestamps[i - 1]
        if gap > 0:
            intervals.append(gap)

    estimated_fps = [round(1.0 / gap, 2) for gap in intervals if gap > 0]
    return {
        "frame_count": len(paths),
        "metrics_available": True,
        "avg_frame_delta": round(sum(deltas) / len(deltas), 5),
        "max_frame_delta": round(max(deltas), 5),
        "estimated_fps_from_timestamps": estimated_fps[:12],
        "avg_estimated_fps": round(sum(estimated_fps) / len(estimated_fps), 2) if estimated_fps else None,
    }
