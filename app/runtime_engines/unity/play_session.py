"""Unity runtime play session — telemetry and artifacts only (no AI)."""
from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional

from app.runtime_engines.base import RuntimeSession
from app.runtime_engines.unity.input_driver import extract_input_trace
from app.runtime_engines.unity.log_parser import merge_log_signals
from app.runtime_engines.unity.models import UnityPlaySessionConfig, UnityPlaySessionResult
from app.runtime_engines.unity.screenshot import analyze_screenshots
from app.runtime_engines.unity.telemetry import ingest_observation_telemetry


def _video_capture_enabled(config: UnityPlaySessionConfig) -> bool:
    if not config.capture_gameplay_video:
        return False
    env = os.environ.get("AI_GRADER_CAPTURE_GAMEPLAY_VIDEO", "1").lower()
    return env in ("1", "true", "yes", "on")


def _start_gameplay_video_capture(session: RuntimeSession, duration_seconds: int) -> Optional[subprocess.Popen]:
    if sys.platform != "win32":
        session.events.record(
            "video_capture_skipped",
            source="play_session",
            reason="platform_not_supported",
        )
        return None

    output = session.artifact_store.gameplay_video / "session_capture.mp4"
    output.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        "ffmpeg",
        "-y",
        "-f",
        "gdigrab",
        "-framerate",
        "10",
        "-i",
        "desktop",
        "-t",
        str(duration_seconds),
        str(output),
    ]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        session.events.record(
            "video_capture_started",
            source="play_session",
            output=str(output),
            duration_seconds=duration_seconds,
        )
        return proc
    except (FileNotFoundError, OSError) as exc:
        session.events.record(
            "video_capture_unavailable",
            source="play_session",
            severity="warning",
            error=str(exc),
        )
        return None


def _stop_gameplay_video_capture(
    session: RuntimeSession,
    proc: Optional[subprocess.Popen],
) -> Optional[str]:
    if not proc:
        return None
    try:
        proc.wait(timeout=8)
    except subprocess.TimeoutExpired:
        proc.kill()
    output = session.artifact_store.gameplay_video / "session_capture.mp4"
    if output.is_file() and output.stat().st_size > 0:
        session.events.record("video_capture_completed", source="play_session", path=str(output))
        return str(output)
    return None


def run_unity_play_session(
    session: RuntimeSession,
    config: UnityPlaySessionConfig,
) -> UnityPlaySessionResult:
    """
    Execute Unity Windows build smoke observation and persist structured artifacts.

    Pipeline:
        Runtime Engine → Telemetry → Artifact Store
    (Gameplay Analysis and AI Evaluation are downstream — not here.)
    """
    started_at = time.time()
    session.events.record(
        "play_session_started",
        source="play_session",
        executable=str(config.executable),
        config=config.to_dict(),
    )

    video_proc: Optional[subprocess.Popen] = None
    if _video_capture_enabled(config):
        video_proc = _start_gameplay_video_capture(session, config.video_duration_seconds)

    try:
        from app.runtime_observation_sandbox import observe_unity_windows_exe

        observation = observe_unity_windows_exe(
            config.executable,
            timeout=config.timeout_seconds,
            session_ctx={"runtime_session_id": session.session_id},
        )
    except Exception as exc:
        session.events.record(
            "play_session_failed",
            source="play_session",
            severity="error",
            error=str(exc),
        )
        _stop_gameplay_video_capture(session, video_proc)
        session.metrics.freeze_detected = True
        return UnityPlaySessionResult(
            observation={
                "status": "partial",
                "runtime_observed": False,
                "crash_detected": True,
                "error": str(exc),
                "freeze_possible": True,
            },
            artifact_paths=session.artifact_store.list_artifacts(),
        )

    video_path = _stop_gameplay_video_capture(session, video_proc)

    screenshot_paths = [
        str(item.get("path"))
        for item in (observation.get("runtime_screenshots") or [])
        if isinstance(item, dict) and item.get("path")
    ]
    screenshot_report = analyze_screenshots(session, screenshot_paths)

    ingest_observation_telemetry(session, observation, started_at=started_at)
    session.metrics.frame_delta_score = float(screenshot_report.get("frame_delta_score") or 0.0)
    session.metrics.freeze_detected = bool(screenshot_report.get("freeze_detected"))
    session.metrics.input_responsive = bool(screenshot_report.get("input_responsive_hint"))
    session.metrics.crash_detected = bool(observation.get("crash_detected"))
    if session.telemetry.avg_fps is not None:
        session.metrics.avg_fps = session.telemetry.avg_fps

    unity_obs = observation.get("unity_observation") or {}
    log_sources = []
    if unity_obs.get("player_log_found") or unity_obs.get("error_count"):
        log_sources.append(
            {
                "source": "player_log",
                "unity_version_hint": unity_obs.get("unity_version_hint", ""),
                "error_count": unity_obs.get("error_count", 0),
                "crash_signal_count": unity_obs.get("crash_signal_count", 0),
                "scene_load_signals": unity_obs.get("scene_load_signals") or [],
                "input_system_signals": unity_obs.get("input_system_signals") or [],
            }
        )
        player_log_path = unity_obs.get("selected_log_path")
        if player_log_path:
            dest = session.artifact_store.logs / "Player.log"
            try:
                src = Path(str(player_log_path))
                if src.is_file():
                    dest.write_text(src.read_text(encoding="utf-8", errors="replace"), encoding="utf-8")
                    session.log_paths.append(dest)
            except OSError:
                pass

    merged_logs = merge_log_signals(*log_sources) if log_sources else {}
    input_trace = extract_input_trace(observation)

    if input_trace:
        trace_path = session.artifact_store.traces / "interaction_trace.json"
        import json

        trace_path.write_text(json.dumps(input_trace, ensure_ascii=False, indent=2), encoding="utf-8")

    session.events.record(
        "play_session_completed",
        source="play_session",
        runtime_observed=bool(observation.get("runtime_observed")),
        screenshot_count=screenshot_report.get("screenshot_count", 0),
    )

    return UnityPlaySessionResult(
        observation=observation,
        screenshot_comparison=screenshot_report,
        merged_log_signals=merged_logs,
        input_trace=input_trace,
        video_path=video_path,
        artifact_paths=session.artifact_store.list_artifacts(),
    )
