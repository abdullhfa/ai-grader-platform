"""Unity runtime telemetry collection — Sprint 2.6."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from app.runtime_engines.base import RuntimeSession
from app.runtime_engines.telemetry import RuntimeTelemetry


def _sample_process_memory_mb(pid: Optional[int]) -> Optional[float]:
    if not pid:
        return None
    try:
        import psutil  # type: ignore

        proc = psutil.Process(pid)
        return round(proc.memory_info().rss / (1024 * 1024), 2)
    except Exception:
        return None


def ingest_observation_telemetry(
    session: RuntimeSession,
    observation: Dict[str, Any],
    *,
    started_at: float,
    process_pid: Optional[int] = None,
) -> RuntimeTelemetry:
    telemetry = session.telemetry
    telemetry.runtime_duration_seconds = round(max(0.0, time.time() - started_at), 2)

    mem = _sample_process_memory_mb(process_pid)
    if mem is not None:
        telemetry.record_memory_mb(mem)

    screenshots = observation.get("runtime_screenshots") or []
    capture_times: List[float] = []
    for shot in screenshots:
        if isinstance(shot, dict) and shot.get("captured_at"):
            try:
                capture_times.append(float(shot["captured_at"]))
            except (TypeError, ValueError):
                pass

    if len(capture_times) >= 2:
        intervals = [
            capture_times[i + 1] - capture_times[i]
            for i in range(len(capture_times) - 1)
            if capture_times[i + 1] > capture_times[i]
        ]
        if intervals:
            fps_telemetry = RuntimeTelemetry.estimate_fps_from_frame_intervals(intervals)
            for sample in fps_telemetry.fps_samples:
                telemetry.record_fps(sample)
            telemetry.frame_times_ms.extend(fps_telemetry.frame_times_ms)

    unity_obs = observation.get("unity_observation") or {}
    for scene_line in unity_obs.get("scene_load_signals") or []:
        telemetry.record_scene_transition(str(scene_line)[:120])

    if observation.get("crash_detected") or unity_obs.get("crash_signal_count"):
        telemetry.record_crash(
            {
                "crash_detected": bool(observation.get("crash_detected")),
                "crash_signal_count": unity_obs.get("crash_signal_count", 0),
            }
        )
        session.events.record(
            "crash_detected",
            source="telemetry",
            severity="error",
            crash_signal_count=unity_obs.get("crash_signal_count", 0),
        )

    if unity_obs.get("visual_states_observed"):
        telemetry.record_ui_event({"visual_states": unity_obs.get("visual_states_observed")})

    fps_file = session.artifact_store.fps / "samples.json"
    fps_file.parent.mkdir(parents=True, exist_ok=True)
    import json

    fps_file.write_text(json.dumps(telemetry.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    session.events.record(
        "telemetry_snapshot",
        source="telemetry",
        avg_fps=telemetry.avg_fps,
        peak_memory_mb=telemetry.peak_memory_mb,
    )
    return telemetry
