"""Lose / game over detection."""
from __future__ import annotations

import re
from typing import List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent

_LOSE = re.compile(r"\b(you lose|game over|try again|defeat|failed|خسارة|حاول مجددا)\b", re.I)


def detect_lose(ocr_text: str, *, timestamp: float = 0.0) -> tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    match = _LOSE.search(ocr_text or "")
    if match:
        events.append(
            GameplayEvent(
                timestamp=timestamp,
                type="lose_detected",
                confidence=0.8,
                payload={"matched_text": match.group(0)},
            )
        )
        return DetectionResult(
            detector="lose_detector",
            label="lose_detected",
            confidence=0.8,
            evidence={"matched_text": match.group(0)},
        ), events
    return DetectionResult(
        detector="lose_detector",
        label="lose_not_detected",
        confidence=0.55,
        evidence={},
    ), events
