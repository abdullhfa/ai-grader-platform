"""Backward-compatible re-exports — use detector.py for new code."""
from app.runtime_engines.unity.detector import (
    detect_confidence,
    detect_unity_layout,
    find_unity_executable,
    find_unity_project_root,
    probe_unity_layout,
    read_unity_version,
)

__all__ = [
    "find_unity_project_root",
    "read_unity_version",
    "find_unity_executable",
    "probe_unity_layout",
    "detect_unity_layout",
    "detect_confidence",
]
