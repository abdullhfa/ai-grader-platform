"""Legacy L4 smoke test engine for .exe / .apk / .pck artifacts."""
from __future__ import annotations

from pathlib import Path
from typing import List

from app.runtime_engines.base import RuntimeEngine, RuntimeSession, SessionStatus
from app.runtime_engines.capabilities import RuntimeCapabilities
from app.runtime_engines.registry import register_engine

_HEAVY_EXTENSIONS = {".exe", ".apk", ".aab", ".pck", ".x86_64"}


def _collect_heavy_artifacts(root: Path) -> List[str]:
    paths: List[str] = []
    if root.is_file() and root.suffix.lower() in _HEAVY_EXTENSIONS:
        return [str(root.resolve())]

    if not root.is_dir():
        return paths

    try:
        from app.runtime_engines.godot.export_runner import is_godot_editor_executable
    except Exception:
        is_godot_editor_executable = None  # type: ignore

    for fp in root.rglob("*"):
        if not fp.is_file():
            continue
        if fp.suffix.lower() not in _HEAVY_EXTENSIONS:
            continue
        if "unitycrashhandler" in fp.name.lower():
            continue
        if is_godot_editor_executable and is_godot_editor_executable(fp):
            continue
        paths.append(str(fp.resolve()))
    return paths[:6]


@register_engine
class LegacyExecutableEngine(RuntimeEngine):
    engine_id = "legacy_exe"
    max_timeout_seconds = 30

    @classmethod
    def capabilities(cls) -> RuntimeCapabilities:
        return RuntimeCapabilities(
            supports_input_simulation=True,
            supports_screenshots=True,
            supports_log_parsing=True,
            supports_telemetry=True,
        )

    @classmethod
    def detect(cls, root: Path) -> float:
        try:
            from app.runtime_engines.godot.export_runner import (
                find_godot_project_root,
                find_godot_runnable_artifacts,
            )

            if find_godot_project_root(root):
                return 0.35
            layout = find_godot_runnable_artifacts(root)
            if layout.get("pck") or layout.get("executable"):
                return 0.35
        except Exception:
            pass

        artifacts = _collect_heavy_artifacts(root)
        if not artifacts:
            return 0.0

        # Defer Unity builds to UnityRuntimeEngine.
        for raw in artifacts:
            if not raw.lower().endswith(".exe"):
                continue
            try:
                from app.runtime_observation_sandbox import detect_unity_build_for_exe

                if detect_unity_build_for_exe(Path(raw)).get("detected"):
                    return 0.45
            except Exception:
                pass

        if any(p.lower().endswith(".pck") for p in artifacts):
            return 0.32
        if any(p.lower().endswith(".exe") for p in artifacts):
            return 0.55
        return 0.32

    def prepare(self, session: RuntimeSession) -> None:
        session.signals["artifact_paths"] = _collect_heavy_artifacts(session.root)

    def execute(self, session: RuntimeSession, *, timeout_seconds: int) -> None:
        paths = session.signals.get("artifact_paths") or []
        if not paths:
            session.status = SessionStatus.SKIPPED
            return

        try:
            from app.runtime_observation_sandbox import observe_runtime_artifacts

            observation = observe_runtime_artifacts(
                paths,
                enable_smoke_test=True,
                student_name=session.submission_key,
            )
        except Exception as exc:
            session.status = SessionStatus.FAILED
            session.errors.append(str(exc))
            return

        session.signals["legacy_observation"] = observation
        session.signals["runtime_method"] = "legacy_smoke_test"
        session.metrics.crash_detected = bool(observation.get("crash_detected"))
        session.metrics.freeze_detected = bool(observation.get("freeze_possible"))

        for shot in observation.get("runtime_screenshots") or []:
            if isinstance(shot, dict) and shot.get("path"):
                session.screenshot_paths.append(Path(str(shot["path"])))

        session.status = (
            SessionStatus.COMPLETED
            if observation.get("status") in ("completed", "partial")
            else SessionStatus.FAILED
        )
