"""Unity build and editor log parsing."""
from __future__ import annotations

import re
from typing import Any, Dict

from app.runtime_observation_sandbox import parse_unity_player_log


def parse_unity_editor_log(log_text: str) -> Dict[str, Any]:
    """Parse Unity Editor batchmode/build log for bounded runtime hints."""
    text = log_text or ""
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    error_re = re.compile(
        r"\b(error|exception|failed|compilation failed|build failed|abort|fatal)\b",
        re.IGNORECASE,
    )
    success_re = re.compile(
        r"\b(build succeeded|build completed|successfully exported|batchmode quit)\b",
        re.IGNORECASE,
    )
    test_re = re.compile(r"\b(test run|passed|failed|run finished)\b", re.IGNORECASE)

    errors = [ln[:240] for ln in lines if error_re.search(ln)]
    successes = [ln[:240] for ln in lines if success_re.search(ln)]
    test_lines = [ln[:240] for ln in lines if test_re.search(ln)]

    player_signals = parse_unity_player_log(text)

    return {
        "error_count": len(errors),
        "error_signals": errors[:12],
        "success_signals": successes[:8],
        "test_signals": test_lines[:12],
        "build_succeeded_hint": len(successes) > 0 and len(errors) == 0,
        "player_log_signals": player_signals,
    }


def merge_log_signals(*logs: Dict[str, Any]) -> Dict[str, Any]:
    merged: Dict[str, Any] = {
        "error_count": 0,
        "crash_signal_count": 0,
        "scene_load_signals": [],
        "input_system_signals": [],
        "sources": [],
    }
    for item in logs:
        if not item:
            continue
        merged["sources"].append(item.get("source", "unknown"))
        merged["error_count"] += int(item.get("error_count") or 0)
        merged["crash_signal_count"] += int(item.get("crash_signal_count") or 0)
        merged["scene_load_signals"].extend(item.get("scene_load_signals") or [])
        merged["input_system_signals"].extend(item.get("input_system_signals") or [])
        if item.get("unity_version_hint"):
            merged["unity_version_hint"] = item["unity_version_hint"]
    merged["scene_load_signals"] = merged["scene_load_signals"][:8]
    merged["input_system_signals"] = merged["input_system_signals"][:6]
    return merged
