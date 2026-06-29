"""Gameplay session and detection result models."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class DetectionResult:
    """Single detector output with confidence — used for corroboration and AI guardrails."""

    detector: str
    label: str
    confidence: float
    evidence: Dict[str, Any] = field(default_factory=dict)
    method: str = "heuristic"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "detector": self.detector,
            "label": self.label,
            "confidence": self.confidence,
            "evidence": self.evidence,
            "method": self.method,
        }


@dataclass
class GameplayEvent:
    timestamp: float
    type: str
    severity: str = "info"
    source: str = "gameplay_ai"
    confidence: float = 0.5
    payload: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "type": self.type,
            "severity": self.severity,
            "source": self.source,
            "confidence": self.confidence,
            "payload": self.payload,
        }


@dataclass
class GameplayTimeline:
    events: List[GameplayEvent] = field(default_factory=list)
    duration_seconds: float = 0.0

    def add(self, event: GameplayEvent) -> None:
        self.events.append(event)
        if event.timestamp > self.duration_seconds:
            self.duration_seconds = event.timestamp

    def sorted_events(self) -> List[GameplayEvent]:
        return sorted(self.events, key=lambda e: e.timestamp)

    def to_dict(self) -> Dict[str, Any]:
        ordered = self.sorted_events()
        return {
            "duration_seconds": self.duration_seconds,
            "event_count": len(ordered),
            "events": [e.to_dict() for e in ordered],
            "summary_lines": [
                f"{int(e.timestamp):02d}s {e.type}" + (f" ({e.confidence:.2f})" if e.confidence else "")
                for e in ordered
            ],
        }


@dataclass
class GameplayRecordingSession:
    """Synchronized gameplay artifact bundle for temporal analysis."""

    session_id: str
    submission_key: str
    artifact_root: Path
    video_path: Optional[Path] = None
    frame_paths: List[Path] = field(default_factory=list)
    frame_timestamps: List[float] = field(default_factory=list)
    telemetry: Dict[str, Any] = field(default_factory=dict)
    runtime_events: List[Dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "session_id": self.session_id,
            "submission_key": self.submission_key,
            "artifact_root": str(self.artifact_root),
            "video_path": str(self.video_path) if self.video_path else None,
            "frame_count": len(self.frame_paths),
            "frame_timestamps": self.frame_timestamps,
            "telemetry": self.telemetry,
            "runtime_event_count": len(self.runtime_events),
        }


@dataclass
class GameplayAnalysisResult:
    session: GameplayRecordingSession
    timeline: GameplayTimeline
    detections: List[DetectionResult] = field(default_factory=list)
    cv_reports: Dict[str, Any] = field(default_factory=dict)
    gameplay_reports: Dict[str, Any] = field(default_factory=dict)
    evidence_links: List[Dict[str, Any]] = field(default_factory=list)
    pipeline_version: str = "gameplay_ai_v1"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "pipeline_version": self.pipeline_version,
            "session": self.session.to_dict(),
            "timeline": self.timeline.to_dict(),
            "detections": [d.to_dict() for d in self.detections],
            "cv_reports": self.cv_reports,
            "gameplay_reports": self.gameplay_reports,
            "evidence_links": self.evidence_links,
        }
