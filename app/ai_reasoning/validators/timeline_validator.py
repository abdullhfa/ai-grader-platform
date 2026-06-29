"""Timeline validator."""
from __future__ import annotations

from typing import Any, Dict, Optional


def validate_timeline(gameplay_analysis: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    gameplay = gameplay_analysis or {}
    timeline = gameplay.get("timeline") or {}
    events = timeline.get("events") or []
    return {
        "valid": len(events) > 0,
        "event_count": len(events),
        "duration_seconds": timeline.get("duration_seconds", 0),
        "issues": [] if events else ["empty_timeline"],
    }
