"""Unity runtime engine — build, play session, telemetry (no AI grading)."""
from __future__ import annotations

import os
from pathlib import Path

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.registry import register_engine
from app.runtime_engines.unity.build_runner import UnityBuildConfig, resolve_unity_binary, run_unity_build
from app.runtime_engines.unity.detector import detect_unity_layout
from app.runtime_engines.unity.hardening import analyze_unity_static_project
from app.runtime_engines.unity.models import UnityPlaySessionConfig
from app.runtime_engines.unity.play_session import run_unity_play_session
from app.runtime_engines.unity.playmode_runner import maybe_run_playmode_tests
from app.runtime_engines.unity.scene_parser import validate_unity_scenes


def _auto_build_enabled() -> bool:
    return os.environ.get("AI_GRADER_UNITY_AUTO_BUILD", "0").lower() in ("1", "true", "yes", "on")


def _playmode_enabled() -> bool:
    return os.environ.get("AI_GRADER_UNITY_PLAYMODE", "0").lower() in ("1", "true", "yes", "on")


def _video_capture_default() -> bool:
    return os.environ.get("AI_GRADER_CAPTURE_GAMEPLAY_VIDEO", "1").lower() in ("1", "true", "yes", "on")


@register_engine
class UnityRuntimeEngine(RuntimeEngine):
    engine_id = "unity"
    max_timeout_seconds = 120

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_headless=True,
            supports_input_simulation=True,
            supports_screenshots=True,
            supports_video_capture=True,
            supports_network_isolation=False,
            supports_gpu=True,
            supports_audio=False,
            supports_build_from_source=True,
            supports_playmode_tests=True,
            supports_log_parsing=True,
            supports_telemetry=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        layout = detect_unity_layout(root)
        if layout.has_build_executable:
            return 0.95
        if layout.has_source_project:
            return 0.82
        return 0.0

    def prepare(self, session: RuntimeSession) -> None:
        layout = detect_unity_layout(session.root)
        session.signals["unity_layout"] = layout.to_dict()
        session.events.record(
            "unity_detected",
            source="unity_engine",
            has_source=layout.has_source_project,
            has_build=layout.has_build_executable,
            scene_count=len(layout.scene_paths),
        )
        if layout.project_root:
            session.signals["project_root"] = str(layout.project_root)
        if layout.executable:
            session.signals["executable"] = str(layout.executable)

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        project_root = Path(session.signals["project_root"]) if session.signals.get("project_root") else None
        executable = Path(session.signals["executable"]) if session.signals.get("executable") else None

        if project_root and project_root.is_dir():
            scene_report = validate_unity_scenes(project_root)
            session.signals["scene_validation"] = scene_report
            session.events.record(
                "scene_validation_complete",
                source="unity_engine",
                validation_passed=scene_report.get("validation_passed"),
                scene_count=scene_report.get("scene_count"),
            )

        if not executable and project_root and _auto_build_enabled():
            unity_bin = resolve_unity_binary()
            if unity_bin:
                session.events.record("unity_build_started", source="unity_engine")
                build_result = run_unity_build(
                    UnityBuildConfig(
                        project_path=project_root,
                        unity_path=unity_bin,
                        output_exe=session.artifact_store.session_root / "build" / "game.exe",
                        log_path=session.artifact_store.logs / "unity_build.log",
                        timeout_seconds=min(timeout_seconds * 10, 900),
                    )
                )
                session.signals["build_attempt"] = build_result
                session.events.record(
                    "unity_build_finished",
                    source="unity_engine",
                    success=bool(build_result.get("success")),
                )
                if build_result.get("artifact"):
                    executable = Path(str(build_result["artifact"]))
                    session.signals["executable"] = str(executable)

        if project_root and _playmode_enabled():
            playmode_result = maybe_run_playmode_tests(
                project_root,
                session.artifact_store.session_root,
                timeout_seconds=min(timeout_seconds * 8, 600),
            )
            session.signals["playmode_attempt"] = playmode_result
            session.events.record(
                "playmode_attempt",
                source="unity_engine",
                skipped=bool(playmode_result.get("skipped")),
                success=bool(playmode_result.get("success")),
            )

        if not executable:
            static = analyze_unity_static_project(project_root) if project_root else {}
            session.signals["unity_static_analysis"] = static
            session.signals["runtime_method"] = "unity_static_only"
            session.status = SessionStatus.COMPLETED
            if project_root:
                session.errors.append("unity_source_without_executable")
            else:
                session.errors.append("unity_executable_not_found")
            return

        try:
            play_result = run_unity_play_session(
                session,
                UnityPlaySessionConfig(
                    executable=executable,
                    timeout_seconds=min(timeout_seconds, self.max_timeout_seconds),
                    capture_gameplay_video=_video_capture_default(),
                    enable_input_simulation=True,
                    video_duration_seconds=min(timeout_seconds, self.max_timeout_seconds),
                ),
            )
        except Exception as exc:
            session.status = SessionStatus.COMPLETED
            session.signals["runtime_method"] = "unity_static_only"
            session.signals["unity_static_analysis"] = (
                analyze_unity_static_project(project_root) if project_root else {}
            )
            session.errors.append(f"unity_play_session_error:{exc}")
            return

        observation = play_result.observation
        session.signals["legacy_observation"] = observation
        session.signals["runtime_method"] = "unity_play_session_v2"
        session.signals["unity_observation"] = observation.get("unity_observation") or {}
        session.signals["screenshot_comparison"] = play_result.screenshot_comparison
        session.signals["merged_log_signals"] = play_result.merged_log_signals
        session.signals["input_trace"] = play_result.input_trace
        session.signals["play_session"] = play_result.to_dict()
        if play_result.video_path:
            session.signals["gameplay_video_path"] = play_result.video_path

        if play_result.merged_log_signals:
            build_attempt = session.signals.get("build_attempt") or {}
            if isinstance(build_attempt, dict) and build_attempt.get("log_analysis"):
                session.signals["merged_log_signals"] = play_result.merged_log_signals

        session.status = (
            SessionStatus.COMPLETED
            if observation.get("status") in ("completed", "partial")
            else SessionStatus.FAILED
        )
        if session.status == SessionStatus.FAILED and project_root:
            session.status = SessionStatus.COMPLETED
            session.signals["runtime_method"] = "unity_static_only"
            session.signals["unity_static_analysis"] = analyze_unity_static_project(project_root)
