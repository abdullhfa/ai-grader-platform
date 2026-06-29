"""Unity screenshot capture and comparison — Sprint 2.7."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any, Dict, List

from app.runtime_engines.base import RuntimeSession


def compare_runtime_screenshots(screenshot_paths: List[str]) -> Dict[str, Any]:
    from app.runtime_engines.web.playwright_runner import _estimate_frame_delta

    paths = [Path(p) for p in screenshot_paths if p]
    existing = [p for p in paths if p.is_file()]
    if len(existing) < 2:
        return {
            "frame_delta_score": 0.0,
            "freeze_detected": False,
            "screenshot_count": len(existing),
            "comparison_available": False,
        }

    delta = _estimate_frame_delta([str(p) for p in existing])
    return {
        "frame_delta_score": delta,
        "freeze_detected": delta < 0.01 and len(existing) >= 3,
        "screenshot_count": len(existing),
        "comparison_available": True,
        "input_responsive_hint": delta > 0.02,
    }


def persist_screenshots(session: RuntimeSession, screenshot_paths: List[str]) -> List[str]:
    stored: List[str] = []
    target_dir = session.artifact_store.screenshots
    target_dir.mkdir(parents=True, exist_ok=True)

    for index, raw in enumerate(screenshot_paths):
        src = Path(raw)
        if not src.is_file():
            continue
        dest = target_dir / f"frame_{index:03d}{src.suffix or '.png'}"
        try:
            shutil.copy2(src, dest)
            stored.append(str(dest))
            session.screenshot_paths.append(dest)
        except OSError:
            continue

    session.events.record(
        "screenshots_persisted",
        source="screenshot",
        count=len(stored),
    )
    return stored


def analyze_screenshots(session: RuntimeSession, screenshot_paths: List[str]) -> Dict[str, Any]:
    stored = persist_screenshots(session, screenshot_paths)
    report = compare_runtime_screenshots(stored)
    session.events.record(
        "screenshot_analysis_complete",
        source="screenshot",
        frame_delta_score=report.get("frame_delta_score"),
        freeze_detected=report.get("freeze_detected"),
    )
    return report
