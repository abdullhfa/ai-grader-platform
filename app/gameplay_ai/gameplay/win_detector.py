"""Win condition detection from OCR + timeline."""
from __future__ import annotations

import re
from typing import List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent

_WIN = re.compile(r"\b(you win|victory|level complete|stage clear|mission complete|فوز|انتصار|اكتمل)\b", re.I)


def detect_win(ocr_text: str, *, timestamp: float = 0.0) -> tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    match = _WIN.search(ocr_text or "")
    if match:
        events.append(
            GameplayEvent(
                timestamp=timestamp,
                type="win_detected",
                confidence=0.82,
                payload={"matched_text": match.group(0)},
            )
        )
        return DetectionResult(
            detector="win_detector",
            label="win_detected",
            confidence=0.82,
            evidence={"matched_text": match.group(0)},
        ), events
    return DetectionResult(
        detector="win_detector",
        label="win_not_detected",
        confidence=0.55,
        evidence={},
    ), events
