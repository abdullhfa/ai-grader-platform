"""Death / fail state heuristics."""
from __future__ import annotations

import re
from typing import List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent

_DEATH = re.compile(r"\b(you died|player died|death|respawn|game over|dead|وفاة|مات)\b", re.I)


def detect_death(ocr_text: str, *, timestamp: float = 0.0) -> tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    match = _DEATH.search(ocr_text or "")
    if match:
        events.append(
            GameplayEvent(
                timestamp=timestamp,
                type="player_death",
                confidence=0.77,
                payload={"matched_text": match.group(0)},
            )
        )
        return DetectionResult(
            detector="death_detector",
            label="death_detected",
            confidence=0.77,
            evidence={"matched_text": match.group(0)},
        ), events
    return DetectionResult("death_detector", "death_not_detected", 0.52, {}), events
