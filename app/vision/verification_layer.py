"""Visual verification — OCR presence, screenshot UI signals."""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.vision")

VISUAL_VERIFY_VERSION = "visual_verification_v1"


def _ocr_text(path: Path) -> str:
    try:
        import pytesseract
        from PIL import Image

        img = Image.open(path)
        return pytesseract.image_to_string(img, lang="eng+ara") or ""
    except Exception:
        return ""


def analyze_runtime_screenshots(obs: Dict[str, Any]) -> Dict[str, Any]:
    shots = obs.get("runtime_screenshots") or []
    analyses: List[Dict[str, Any]] = []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        path_str = shot.get("path") or shot.get("file_path") or ""
        if not path_str:
            continue
        path = Path(path_str)
        if not path.is_file():
            continue
        ocr = _ocr_text(path)
        stats = shot.get("visual_stats") or {}
        analyses.append(
            {
                "path": str(path),
                "visual_state": shot.get("visual_state"),
                "ocr_char_count": len(ocr.strip()),
                "ocr_has_ui_text": len(ocr.strip()) > 8,
                "black_screen_possible": stats.get("black_screen_possible"),
            }
        )
    ui_verified = any(a.get("ocr_has_ui_text") for a in analyses) or any(
        a.get("visual_state") not in (None, "black_screen", "unknown") for a in analyses
    )
    return {
        "version": VISUAL_VERIFY_VERSION,
        "screenshot_count": len(analyses),
        "analyses": analyses,
        "ui_verification_hint": ui_verified,
        "advisory_only": True,
    }


def attach_visual_verification(
    grading_result: Dict[str, Any],
    observation: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    obs = observation or (grading_result.get("artifact_inventory") or {}).get(
        "runtime_observation_report"
    ) or {}
    report = analyze_runtime_screenshots(obs)
    grading_result["visual_verification"] = report
    inv = grading_result.setdefault("artifact_inventory", {})
    inv["visual_verification"] = report
    logger.info("visual_verification screenshots=%d", report["screenshot_count"])
    return grading_result
