"""OCR layer for HUD text — tesseract primary, easyocr optional."""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Tuple

from app.gameplay_ai.session_model import DetectionResult

_SCORE_RE = re.compile(r"\b(score|points?|coins?|health|hp|lives|level|wave|time|timer|fps)\s*[:\-]?\s*(\d+)", re.I)
_WIN_RE = re.compile(r"\b(you win|victory|level complete|stage clear|فوز|انتصار)\b", re.I)
_LOSE_RE = re.compile(r"\b(you lose|game over|try again|defeat|dead|خسارة|حاول)\b", re.I)
_PAUSE_RE = re.compile(r"\b(paused|pause menu|resume|متوقف)\b", re.I)


def _ocr_tesseract(path: Path) -> Tuple[str, str]:
    try:
        import pytesseract  # type: ignore
        from PIL import Image

        text = pytesseract.image_to_string(Image.open(path).convert("RGB"), lang="eng", config="--psm 6")
        return (text or "").strip(), "tesseract"
    except Exception:
        return "", "unavailable"


def _ocr_easyocr(path: Path) -> Tuple[str, str]:
    try:
        import easyocr  # type: ignore

        reader = easyocr.Reader(["en"], gpu=False, verbose=False)
        lines = reader.readtext(str(path), detail=0)
        return "\n".join(lines), "easyocr"
    except Exception:
        return "", "unavailable"


def ocr_frame(path: Path) -> Dict[str, Any]:
    text, method = _ocr_tesseract(path)
    if len(text) < 4:
        alt, alt_method = _ocr_easyocr(path)
        if len(alt) > len(text):
            text, method = alt, alt_method
    return {"path": str(path), "text": text[:2000], "method": method}


def analyze_frames_ocr(paths: List[Path], *, max_frames: int = 12) -> DetectionResult:
    texts: List[Dict[str, Any]] = []
    combined = ""
    for fp in paths[:max_frames]:
        row = ocr_frame(fp)
        texts.append(row)
        combined += "\n" + row.get("text", "")

    scores = _SCORE_RE.findall(combined)
    wins = bool(_WIN_RE.search(combined))
    loses = bool(_LOSE_RE.search(combined))
    pauses = bool(_PAUSE_RE.search(combined))

    confidence = 0.75 if (scores or wins or loses) else 0.35
    if any(t.get("method") == "tesseract" and t.get("text") for t in texts):
        confidence = min(0.92, confidence + 0.1)

    return DetectionResult(
        detector="text_ocr",
        label="hud_text_extracted" if combined.strip() else "no_text",
        confidence=confidence,
        evidence={
            "frames_ocrd": len(texts),
            "score_tokens": scores[:10],
            "win_text": wins,
            "lose_text": loses,
            "pause_text": pauses,
            "samples": texts[:6],
        },
        method="tesseract_or_easyocr",
    )


def combined_ocr_text(paths: List[Path]) -> str:
    parts = []
    for fp in paths[:12]:
        parts.append(ocr_frame(fp).get("text", ""))
    return "\n".join(parts)
