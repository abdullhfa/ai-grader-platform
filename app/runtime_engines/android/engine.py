"""Android runtime engine — PRO emulator farm + UI automation."""
from __future__ import annotations

from pathlib import Path

from app.runtime_engines.android.project_probe import detect_project_stack, find_apk_artifact, submission_has_android_artifacts
from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.registry import register_engine


@register_engine
class AndroidRuntimeEngine(RuntimeEngine):
    engine_id = "android"
    max_timeout_seconds = 90

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=False,
            supports_input_simulation=True,
            supports_screenshots=True,
            supports_video_capture=True,
            supports_log_parsing=True,
            supports_telemetry=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        if not submission_has_android_artifacts(root):
            return 0.0
        probe = detect_project_stack(root)
        if probe.get("apk_path"):
            return 0.88
        if probe.get("flutter"):
            return 0.82
        if probe.get("kotlin") or probe.get("java"):
            return 0.78
        return 0.72

    def prepare(self, session: RuntimeSession) -> None:
        probe = detect_project_stack(session.root)
        apk_raw = probe.get("apk_path")
        session.signals["android_probe"] = probe
        if apk_raw:
            session.signals["apk_path"] = apk_raw

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        use_emulator = bool(session.signals.get("enable_android_emulator_automation"))
        if not use_emulator:
            session.status = SessionStatus.SKIPPED
            session.signals["android_skipped"] = "basic_mode_or_flag_off"
            return

        from app.runtime_engines.android.mobile_automation import run_android_mobile_automation

        apk_path = session.signals.get("apk_path")
        entry = Path(apk_path) if apk_path else find_apk_artifact(session.root)
        shot_dir = session.workspace / "android_screenshots"
        result = run_android_mobile_automation(
            session.root,
            apk_path=entry,
            timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
            screenshot_dir=shot_dir,
        )

        session.signals.update(result.get("signals") or {})
        session.signals["runtime_method"] = result.get("method", "unknown")
        if result.get("android_mobile_automation"):
            session.signals["android_mobile_automation"] = result["android_mobile_automation"]
        if result.get("ui_steps"):
            session.signals["ui_steps"] = result["ui_steps"]
        session.screenshot_paths = [Path(p) for p in result.get("screenshots") or []]
        for rec in result.get("screen_recordings") or []:
            session.signals.setdefault("screen_recordings", []).append(rec)

        if result.get("console_errors"):
            session.signals["console_errors"] = result["console_errors"]

        if result.get("success"):
            session.status = SessionStatus.COMPLETED
        elif result.get("method") == "static_only":
            session.status = SessionStatus.COMPLETED
            session.signals["emulator_unavailable"] = True
        else:
            session.status = SessionStatus.FAILED
            if result.get("error"):
                session.errors.append(str(result["error"]))
