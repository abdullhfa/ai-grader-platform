"""Unity runtime domain models — no AI logic."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


@dataclass
class UnityDetectionResult:
    project_root: Optional[Path] = None
    executable: Optional[Path] = None
    unity_version: str = ""
    scene_paths: List[str] = field(default_factory=list)
    has_source_project: bool = False
    has_build_executable: bool = False
    build_confidence: str = "none"
    detection_method: str = "layout_probe"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "project_root": str(self.project_root) if self.project_root else None,
            "executable": str(self.executable) if self.executable else None,
            "unity_version": self.unity_version,
            "scene_paths": self.scene_paths,
            "scene_count": len(self.scene_paths),
            "has_source_project": self.has_source_project,
            "has_build_executable": self.has_build_executable,
            "build_confidence": self.build_confidence,
            "detection_method": self.detection_method,
        }


@dataclass
class UnityPlaySessionConfig:
    executable: Path
    timeout_seconds: int = 30
    capture_screenshots: bool = True
    capture_gameplay_video: bool = False
    enable_input_simulation: bool = True
    video_duration_seconds: int = 12

    def to_dict(self) -> Dict[str, Any]:
        return {
            "executable": str(self.executable),
            "timeout_seconds": self.timeout_seconds,
            "capture_screenshots": self.capture_screenshots,
            "capture_gameplay_video": self.capture_gameplay_video,
            "enable_input_simulation": self.enable_input_simulation,
            "video_duration_seconds": self.video_duration_seconds,
        }


@dataclass
class UnityPlaySessionResult:
    observation: Dict[str, Any] = field(default_factory=dict)
    screenshot_comparison: Dict[str, Any] = field(default_factory=dict)
    merged_log_signals: Dict[str, Any] = field(default_factory=dict)
    input_trace: Dict[str, Any] = field(default_factory=dict)
    video_path: Optional[str] = None
    artifact_paths: Dict[str, List[str]] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "observation": self.observation,
            "screenshot_comparison": self.screenshot_comparison,
            "merged_log_signals": self.merged_log_signals,
            "input_trace": self.input_trace,
            "video_path": self.video_path,
            "artifact_paths": self.artifact_paths,
        }
