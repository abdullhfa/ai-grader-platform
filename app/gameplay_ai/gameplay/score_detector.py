"""Score / health numeric extraction from OCR."""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent

_SCORE = re.compile(
    r"\b(score|points?|coins?|health|hp|lives|level|wave|timer|time)\s*[:\-]?\s*(\d+)",
    re.I,
)


def detect_score_changes(ocr_text: str, *, timestamp: float = 0.0) -> Tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    tokens = _SCORE.findall(ocr_text or "")
    if not tokens:
        return DetectionResult(
            detector="score_detector",
            label="no_score_tokens",
            confidence=0.4,
            evidence={},
        ), events

    parsed = [{"key": k.lower(), "value": int(v)} for k, v in tokens[:12]]
    events.append(
        GameplayEvent(
            timestamp=timestamp,
            type="score_tokens_detected",
            confidence=0.78,
            payload={"tokens": parsed},
        )
    )
    return DetectionResult(
        detector="score_detector",
        label="score_hud_detected",
        confidence=min(0.9, 0.5 + len(parsed) * 0.08),
        evidence={"tokens": parsed},
    ), events
