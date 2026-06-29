"""UI element heuristics — menus, buttons, overlays."""
from __future__ import annotations

from pathlib import Path
from typing import List

from app.gameplay_ai.session_model import DetectionResult


def detect_ui_elements(paths: List[Path]) -> DetectionResult:
    from app.gameplay_ai.cv.text_ocr import combined_ocr_text, ocr_frame

    if not paths:
        return DetectionResult("ui_detector", "no_frames", 0.2, {})

    menu_keywords = ("play", "start", "menu", "settings", "quit", "continue", "ابدأ", "قائمة")
    hits = 0
    for fp in paths[:6]:
        text = ocr_frame(fp).get("text", "").lower()
        if any(k in text for k in menu_keywords):
            hits += 1

    combined = combined_ocr_text(paths[:4]).lower()
    menu_detected = hits > 0 or "main menu" in combined or "title screen" in combined
    confidence = min(0.88, 0.4 + hits * 0.15)
    return DetectionResult(
        detector="ui_detector",
        label="menu_ui_detected" if menu_detected else "gameplay_ui_unclear",
        confidence=confidence,
        evidence={"menu_keyword_hits": hits},
        method="ocr_keyword",
    )
