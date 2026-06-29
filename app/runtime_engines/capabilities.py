"""Runtime engine capability matrix — used for scheduling and pipeline routing."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class RuntimeCapabilities:
    supports_headless: bool = False
    supports_input_simulation: bool = False
    supports_screenshots: bool = False
    supports_video_capture: bool = False
    supports_network_isolation: bool = False
    supports_gpu: bool = False
    supports_audio: bool = False
    supports_build_from_source: bool = False
    supports_playmode_tests: bool = False
    supports_log_parsing: bool = False
    supports_telemetry: bool = False

    def to_dict(self) -> dict:
        return {
            "supports_headless": self.supports_headless,
            "supports_input_simulation": self.supports_input_simulation,
            "supports_screenshots": self.supports_screenshots,
            "supports_video_capture": self.supports_video_capture,
            "supports_network_isolation": self.supports_network_isolation,
            "supports_gpu": self.supports_gpu,
            "supports_audio": self.supports_audio,
            "supports_build_from_source": self.supports_build_from_source,
            "supports_playmode_tests": self.supports_playmode_tests,
            "supports_log_parsing": self.supports_log_parsing,
            "supports_telemetry": self.supports_telemetry,
        }
