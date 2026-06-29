"""Headless web game runner — Playwright with static fallback."""
from __future__ import annotations

import importlib
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.runtime.web")


def _file_uri(path: Path) -> str:
    resolved = path.resolve().as_posix()
    if len(resolved) >= 2 and resolved[1] == ":":
        return "file:///" + resolved
    return "file://" + resolved


def _static_web_analysis(path: Path) -> Dict[str, Any]:
    content = ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:50000]
    except OSError as exc:
        return {"success": False, "error": str(exc), "method": "static_only"}

    lower = content.lower()
    return {
        "success": True,
        "method": "static_only",
        "signals": {
            "html_valid": bool(content.strip()),
            "has_script": "<script" in lower,
            "has_canvas": "<canvas" in lower,
            "interactive_hint": "<script" in lower or "<canvas" in lower,
        },
        "screenshots": [],
        "console_errors": [],
    }


def run_web_game_headless(
    index_html: Path,
    *,
    timeout_ms: int = 15000,
    frame_count: int = 5,
    screenshot_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    Launch HTML/JS game in headless Chromium when Playwright is available.
    Falls back to static HTML analysis otherwise.
    """
    if not index_html.is_file():
        return {"success": False, "error": "index_html_missing", "method": "none"}

    try:
        sync_api = importlib.import_module("playwright.sync_api")
        sync_playwright = sync_api.sync_playwright
    except ImportError:
        logger.info("Playwright not installed — using static web analysis for %s", index_html)
        return _static_web_analysis(index_html)

    out_dir = screenshot_dir or (index_html.parent / ".runtime_screenshots")
    out_dir.mkdir(parents=True, exist_ok=True)

    screenshots: List[str] = []
    console_errors: List[str] = []
    page_errors: List[str] = []
    navigation_ok = False

    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})

            def _on_console(msg):
                if msg.type == "error":
                    console_errors.append(msg.text[:500])

            def _on_page_error(exc):
                page_errors.append(str(exc)[:500])

            page.on("console", _on_console)
            page.on("pageerror", _on_page_error)

            try:
                page.goto(_file_uri(index_html), wait_until="domcontentloaded", timeout=timeout_ms)
                navigation_ok = True
            except Exception as exc:
                page_errors.append(f"navigation_failed: {exc}")

            interval = max(500, timeout_ms // max(frame_count, 1))
            for i in range(frame_count):
                page.wait_for_timeout(interval)
                shot_path = out_dir / f"frame_{i:02d}.png"
                try:
                    page.screenshot(path=str(shot_path), full_page=False)
                    screenshots.append(str(shot_path))
                except Exception as exc:
                    page_errors.append(f"screenshot_{i}: {exc}")

                for key in ("ArrowRight", "ArrowLeft", "Space", "Enter"):
                    try:
                        page.keyboard.press(key)
                    except Exception:
                        pass

            browser.close()
    except Exception as exc:
        logger.warning("Playwright runtime failed for %s: %s", index_html, exc)
        fallback = _static_web_analysis(index_html)
        fallback["playwright_error"] = str(exc)
        return fallback

    frame_delta = _estimate_frame_delta(screenshots)
    return {
        "success": navigation_ok,
        "method": "playwright_headless",
        "signals": {
            "html_valid": True,
            "navigation_ok": navigation_ok,
            "has_script": True,
            "interactive_hint": True,
            "screenshot_count": len(screenshots),
            "console_error_count": len(console_errors),
            "page_error_count": len(page_errors),
            "frame_delta_score": frame_delta,
            "freeze_detected": frame_delta < 0.01 and len(screenshots) >= 3,
            "input_simulated": True,
        },
        "screenshots": screenshots,
        "console_errors": console_errors[:20],
        "page_errors": page_errors[:20],
    }


def _estimate_frame_delta(screenshot_paths: List[str]) -> float:
    if len(screenshot_paths) < 2:
        return 0.0
    try:
        from PIL import Image, ImageChops
    except ImportError:
        return 0.0

    deltas: List[float] = []
    prev = Image.open(screenshot_paths[0]).convert("L").resize((160, 90))
    for raw in screenshot_paths[1:]:
        curr = Image.open(raw).convert("L").resize((160, 90))
        diff = ImageChops.difference(prev, curr)
        pixels = list(diff.getdata())
        mean_delta = sum(pixels) / (160 * 90 * 255)
        deltas.append(mean_delta)
        prev = curr
    if not deltas:
        return 0.0
    return min(1.0, (sum(deltas) / len(deltas)) * 8.0)


def find_web_entry_point(root: Path) -> Optional[Path]:
    if root.is_file() and root.suffix.lower() in {".html", ".htm"}:
        return root
    if not root.is_dir():
        return None

    preferred = root / "index.html"
    if preferred.is_file():
        return preferred

    html_files = sorted(root.rglob("*.html"))
    html_files = [p for p in html_files if "node_modules" not in p.parts]
    if not html_files:
        html_files = sorted(root.rglob("*.htm"))
    if not html_files:
        return None

    named_index = [p for p in html_files if p.name.lower() == "index.html"]
    return named_index[0] if named_index else html_files[0]
