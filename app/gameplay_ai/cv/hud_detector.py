"""HUD region heuristics — score/health/timer presence."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List

from app.gameplay_ai.session_model import DetectionResult


def detect_hud_regions(paths: List[Path]) -> DetectionResult:
    if not paths:
        return DetectionResult("hud_detector", "no_frames", 0.2, {})

    try:
        from PIL import Image, ImageStat
    except ImportError:
        return DetectionResult("hud_detector", "pil_unavailable", 0.1, {})

    hud_hits = 0
    samples: List[Dict[str, Any]] = []
    for fp in paths[:8]:
        img = Image.open(fp).convert("L")
        w, h = img.size
        # Top band (score/timer) + bottom band (health/ammo)
        top = img.crop((0, 0, w, max(1, h // 6)))
        bottom = img.crop((0, h - max(1, h // 6), w, h))
        top_var = ImageStat.Stat(top).var[0]
        bottom_var = ImageStat.Stat(bottom).var[0]
        center = img.crop((w // 4, h // 4, 3 * w // 4, 3 * h // 4))
        center_var = ImageStat.Stat(center).var[0]
        # HUD often = high edge variance in bands vs calmer center OR text contrast
        band_activity = (top_var + bottom_var) / 2.0
        hud_like = band_activity > center_var * 0.35 and band_activity > 100
        if hud_like:
            hud_hits += 1
        samples.append(
            {
                "path": str(fp),
                "top_var": round(top_var, 2),
                "bottom_var": round(bottom_var, 2),
                "center_var": round(center_var, 2),
                "hud_like": hud_like,
            }
        )

    ratio = hud_hits / max(len(samples), 1)
    label = "hud_likely" if ratio >= 0.4 else "hud_unclear"
    confidence = min(0.9, 0.45 + ratio * 0.5)
    return DetectionResult(
        detector="hud_detector",
        label=label,
        confidence=confidence,
        evidence={"hud_frame_ratio": round(ratio, 3), "samples": samples},
        method="band_variance_heuristic",
    )
