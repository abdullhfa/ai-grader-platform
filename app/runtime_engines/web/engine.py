"""Web runtime engine — HTML5 / canvas games."""
from __future__ import annotations

from pathlib import Path

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.registry import register_engine
from app.runtime_engines.web.playwright_runner import find_web_entry_point, run_web_game_headless


@register_engine
class WebRuntimeEngine(RuntimeEngine):
    engine_id = "web"
    max_timeout_seconds = 30

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=True,
            supports_input_simulation=True,
            supports_screenshots=True,
            supports_video_capture=False,
            supports_log_parsing=False,
            supports_telemetry=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        entry = find_web_entry_point(root)
        if not entry:
            return 0.0
        try:
            content = entry.read_text(encoding="utf-8", errors="replace")[:20000].lower()
        except OSError:
            return 0.4
        score = 0.55
        if "<canvas" in content:
            score += 0.25
        if "<script" in content:
            score += 0.15
        if entry.name.lower() == "index.html":
            score += 0.05
        return min(1.0, score)

    def prepare(self, session: RuntimeSession) -> None:
        entry = find_web_entry_point(session.root)
        if not entry:
            session.errors.append("web_entry_not_found")
            session.status = SessionStatus.SKIPPED
            return
        session.signals["entry_html"] = str(entry)

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        entry_raw = session.signals.get("entry_html")
        if not entry_raw:
            session.status = SessionStatus.SKIPPED
            return

        entry = Path(entry_raw)
        shot_dir = session.workspace / "screenshots"
        use_browser = bool(session.signals.get("enable_web_browser_automation"))

        if use_browser:
            from app.runtime_engines.web.browser_automation import run_web_browser_automation

            result = run_web_browser_automation(
                session.root,
                entry,
                timeout_ms=min(timeout_seconds, self.max_timeout_seconds) * 1000,
                screenshot_dir=shot_dir,
            )
        else:
            result = run_web_game_headless(
                entry,
                timeout_ms=min(timeout_seconds, self.max_timeout_seconds) * 1000,
                screenshot_dir=shot_dir,
            )

        session.signals.update(result.get("signals") or {})
        session.signals["runtime_method"] = result.get("method", "unknown")
        if result.get("web_browser_automation"):
            session.signals["web_browser_automation"] = result["web_browser_automation"]
        if result.get("navigation_steps"):
            session.signals["navigation_steps"] = result["navigation_steps"]
        if result.get("http_errors"):
            session.signals["http_errors"] = result["http_errors"]
        session.screenshot_paths = [Path(p) for p in result.get("screenshots") or []]
        session.metrics.frame_delta_score = float(
            (result.get("signals") or {}).get("frame_delta_score") or 0.0
        )
        session.metrics.freeze_detected = bool(
            (result.get("signals") or {}).get("freeze_detected")
        )
        session.metrics.input_responsive = session.metrics.frame_delta_score > 0.02

        if result.get("page_errors") or result.get("console_errors"):
            session.signals["console_errors"] = result.get("console_errors") or []
            session.signals["page_errors"] = result.get("page_errors") or []

        if result.get("success"):
            session.status = SessionStatus.COMPLETED
        elif result.get("method") == "static_only":
            session.status = SessionStatus.COMPLETED
            session.signals["headless_unavailable"] = True
        else:
            session.status = SessionStatus.FAILED
            if result.get("error"):
                session.errors.append(str(result["error"]))
