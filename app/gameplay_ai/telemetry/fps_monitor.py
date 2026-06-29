"""Telemetry ingestion for gameplay pipeline."""
from __future__ import annotations

from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent


def analyze_fps(telemetry: Dict[str, Any]) -> DetectionResult:
    samples = telemetry.get("fps_samples") or []
    avg = telemetry.get("avg_fps")
    if not samples and avg is None:
        return DetectionResult("fps_monitor", "no_fps_data", 0.25, {})

    avg_val = float(avg) if avg is not None else sum(samples) / len(samples)
    low_fps = avg_val < 20
    return DetectionResult(
        detector="fps_monitor",
        label="low_fps" if low_fps else "fps_ok",
        confidence=0.8,
        evidence={"avg_fps": round(avg_val, 2), "sample_count": len(samples)},
    )


def telemetry_to_events(telemetry: Dict[str, Any]) -> List[GameplayEvent]:
    events: List[GameplayEvent] = []
    for scene in telemetry.get("scene_transitions") or []:
        events.append(
            GameplayEvent(
                timestamp=0.0,
                type="scene_loaded",
                confidence=0.85,
                source="telemetry",
                payload={"scene_line": str(scene)[:200]},
            )
        )
    for crash in telemetry.get("crash_events") or []:
        events.append(
            GameplayEvent(
                timestamp=0.0,
                type="crash_event",
                severity="error",
                confidence=0.9,
                source="telemetry",
                payload=crash if isinstance(crash, dict) else {"detail": str(crash)},
            )
        )
    return events
