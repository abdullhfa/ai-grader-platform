"""Pause menu detection."""
from __future__ import annotations

import re
from typing import List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent

_PAUSE = re.compile(r"\b(paused|pause menu|resume|game paused|متوقف)\b", re.I)


def detect_pause(ocr_text: str, *, timestamp: float = 0.0) -> tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    if _PAUSE.search(ocr_text or ""):
        events.append(GameplayEvent(timestamp=timestamp, type="pause_detected", confidence=0.76))
        return DetectionResult(
            detector="pause_detector",
            label="pause_detected",
            confidence=0.76,
            evidence={},
        ), events
    return DetectionResult("pause_detector", "pause_not_detected", 0.5, {}), events
