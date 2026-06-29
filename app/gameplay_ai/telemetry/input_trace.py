"""Input trace correlation from runtime artifacts."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from app.gameplay_ai.session_model import GameplayEvent


def load_input_trace(artifact_root: Path) -> Dict[str, Any]:
    trace_path = artifact_root / "traces" / "interaction_trace.json"
    if trace_path.is_file():
        try:
            return json.loads(trace_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def input_trace_to_events(trace: Dict[str, Any]) -> List[GameplayEvent]:
    if not trace:
        return []
    events: List[GameplayEvent] = []
    if trace.get("status") == "completed":
        events.append(
            GameplayEvent(
                timestamp=3.5,
                type="input_simulated",
                confidence=0.75,
                source="input_trace",
                payload={
                    "input_count": trace.get("input_count"),
                    "visual_response": trace.get("visual_response_to_input"),
                },
            )
        )
    return events
