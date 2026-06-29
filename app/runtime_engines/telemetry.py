"""Runtime telemetry — measurable signals separate from AI evaluation."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RuntimeTelemetry:
    fps_samples: List[float] = field(default_factory=list)
    frame_times_ms: List[float] = field(default_factory=list)
    memory_usage_mb: List[float] = field(default_factory=list)
    scene_transitions: List[str] = field(default_factory=list)
    crash_events: List[Dict[str, Any]] = field(default_factory=list)
    ui_events: List[Dict[str, Any]] = field(default_factory=list)
    process_exit_code: Optional[int] = None
    runtime_duration_seconds: Optional[float] = None
    avg_fps: Optional[float] = None
    peak_memory_mb: Optional[float] = None

    def record_fps(self, value: float) -> None:
        self.fps_samples.append(value)
        if self.fps_samples:
            self.avg_fps = round(sum(self.fps_samples) / len(self.fps_samples), 2)

    def record_memory_mb(self, value: float) -> None:
        self.memory_usage_mb.append(value)
        self.peak_memory_mb = max(self.peak_memory_mb or 0.0, value)

    def record_scene_transition(self, scene_name: str) -> None:
        if scene_name and scene_name not in self.scene_transitions:
            self.scene_transitions.append(scene_name)

    def record_crash(self, detail: Dict[str, Any]) -> None:
        self.crash_events.append(detail)

    def record_ui_event(self, detail: Dict[str, Any]) -> None:
        self.ui_events.append(detail)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def estimate_fps_from_frame_intervals(cls, intervals_seconds: List[float]) -> "RuntimeTelemetry":
        telemetry = cls()
        for interval in intervals_seconds:
            if interval > 0:
                telemetry.record_fps(round(1.0 / interval, 2))
                telemetry.frame_times_ms.append(round(interval * 1000.0, 2))
        return telemetry
