"""Level / scene progression from temporal scene changes + OCR."""
from __future__ import annotations

from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult, GameplayEvent


def detect_progression(
    scene_change_evidence: Dict[str, Any],
    ocr_text: str,
    *,
    base_timestamp: float = 0.0,
) -> tuple[DetectionResult, List[GameplayEvent]]:
    events: List[GameplayEvent] = []
    changes = scene_change_evidence.get("changes") or []
    level_keywords = ("level", "stage", "world", "wave", "mission", "مرحلة", "مستوى")
    ocr_lower = (ocr_text or "").lower()
    keyword_hit = any(k in ocr_lower for k in level_keywords)

    if changes:
        for change in changes[:5]:
            events.append(
                GameplayEvent(
                    timestamp=float(change.get("timestamp") or base_timestamp),
                    type="progression_scene_change",
                    confidence=0.7,
                    payload=change,
                )
            )

    progressed = len(changes) >= 1 or keyword_hit
    confidence = min(0.88, 0.45 + len(changes) * 0.12 + (0.15 if keyword_hit else 0))
    return DetectionResult(
        detector="progression_detector",
        label="progression_detected" if progressed else "progression_unclear",
        confidence=confidence,
        evidence={"scene_changes": len(changes), "level_keywords_in_ocr": keyword_hit},
    ), events
