"""GameMaker runtime execution — EXE smoke + HTML5 delegation."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime_engines.base import RuntimeSession, SessionStatus
from app.runtime_engines.gamemaker.sandbox_provider import (
    GameMakerSandboxProvider,
    assess_gamemaker_sandbox_readiness,
)


def _unsupported_observation(readiness: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "status": "skipped", "runtime_status": "SKIPPED_UNSUPPORTED_ENVIRONMENT",
        "completion_scope": "COMPLETED_STATIC_ONLY", "contract_id": "gamemaker_exe_smoke",
        "verification_outcome": "NOT_VERIFIED", "verification_blocker_origin": "SYSTEM",
        "reason_code": "RUNTIME_ENVIRONMENT_UNSUPPORTED",
        "user_message_ar": "لم يُنفّذ اختبار اللعبة لأن بيئة Windows Sandbox غير متاحة؛ أُكمل التحليل الساكن فقط.",
        "runtime_attempted": False,
        "game_launch_attempted": False, "runtime_gate_passed": False, "evidence_count": 0,
        "academic_runtime_verified": False, "runtime_screenshots": [],
        "sandbox_readiness": readiness, "errors": ["windows_sandbox_unavailable"],
    }


def run_exe_smoke(session: RuntimeSession, executable: Path, *, timeout_seconds: int,
                  provider: Optional[GameMakerSandboxProvider] = None) -> Dict[str, Any]:
    try:
        from app.runtime_engines.gamemaker.project_probe import assess_gamemaker_exe_launch
        from app.runtime_observation_sandbox import resolve_smoke_timeout_seconds

        exe = executable.resolve()
        search_root = session.root if session.root else None
        # The session root is the security boundary.  Never discover sibling uploads.
        if search_root is not None:
            search_root = search_root.resolve()
            try:
                exe.relative_to(search_root)
            except ValueError:
                raise ValueError("RUNTIME_EVIDENCE_IDENTITY_MISMATCH: executable outside submission_root")

        sandbox_provider, readiness = assess_gamemaker_sandbox_readiness(
            executable=exe, submission_root=search_root, provider=provider
        )
        if sandbox_provider is None or not readiness.ready:
            observation = _unsupported_observation(readiness.to_dict())
            session.signals["gamemaker_observation"] = observation
            session.signals["runtime_method"] = "gamemaker_runtime_unavailable"
            session.signals["runtime_status"] = observation["runtime_status"]
            session.signals["completion_scope"] = observation["completion_scope"]
            session.status = SessionStatus.SKIPPED
            return {"success": False, "observation": observation, "skipped": True, "reason": observation["reason_code"]}
        launch_assessment = assess_gamemaker_exe_launch(exe, search_root=search_root)
        runtime_cwd = Path(launch_assessment.get("runtime_cwd") or exe.parent)
        session.signals["gamemaker_runtime_cwd"] = str(runtime_cwd)
        session.signals["gamemaker_launch_assessment"] = launch_assessment

        if launch_assessment.get("is_gamemaker") and not launch_assessment.get("launch_allowed"):
            observation = {
                "status": "skipped",
                "contract_id": "gamemaker_exe_smoke",
                "runtime_screenshots": [],
                "crash_detected": False,
                "freeze_possible": False,
                "analyses": [],
                "gamemaker_runtime_cwd": str(runtime_cwd),
                "runtime_attempted": False,
                "game_launch_attempted": False,
                "sandbox_readiness": readiness.to_dict(),
                "skip_reason": launch_assessment.get("skip_reason") or "missing_data_win",
                "errors": ["gamemaker_missing_data_win"],
            }
            session.signals["gamemaker_observation"] = observation
            session.signals["runtime_method"] = "gamemaker_static_only"
            session.status = SessionStatus.COMPLETED
            return {
                "success": True,
                "observation": observation,
                "skipped": True,
                "reason": observation["skip_reason"],
            }

        smoke = sandbox_provider.launch_and_observe(
            executable=exe,
            runtime_cwd=runtime_cwd,
            timeout_seconds=min(timeout_seconds, resolve_smoke_timeout_seconds("deep")),
            session_context={
                "student_name": session.submission_key,
                "submission_root": str(search_root) if search_root else None,
                "project_root": str(search_root) if search_root else None,
            },
        )
        smoke_ok = smoke.get("smoke_result") in ("stable_window", "launch_ok")
        observation = {
            "status": "completed" if smoke_ok else "partial",
            "contract_id": "gamemaker_exe_smoke",
            "runtime_screenshots": smoke.get("runtime_screenshots") or [],
            "crash_detected": smoke.get("signals", {}).get("crash") == "detected",
            "freeze_possible": bool((smoke.get("visual_observation") or {}).get("freeze_possible")),
            "analyses": [smoke],
            "gamemaker_runtime_cwd": str(runtime_cwd),
            "runtime_attempted": bool(smoke.get("attempted")),
            "game_launch_attempted": bool(smoke.get("attempted")),
            "sandbox_readiness": readiness.to_dict(),
        }
        if smoke.get("errors"):
            observation["errors"] = smoke["errors"]
        if not smoke.get("attempted"):
            observation["status"] = "skipped"
    except Exception as exc:
        session.status = SessionStatus.FAILED
        session.errors.append(str(exc))
        return {"success": False, "error": str(exc)}

    session.signals["gamemaker_observation"] = observation
    session.signals["runtime_method"] = "gamemaker_exe_smoke"
    session.metrics.crash_detected = bool(observation.get("crash_detected"))
    session.metrics.freeze_detected = bool(observation.get("freeze_possible"))

    runtime_shots = observation.get("runtime_screenshots")
    shots: List[Any] = (
        runtime_shots if isinstance(runtime_shots, list) else []
    )
    for shot in shots:
        if isinstance(shot, dict) and shot.get("path"):
            session.screenshot_paths.append(Path(str(shot["path"])))

    session.status = (
        SessionStatus.COMPLETED
        if observation.get("status") in ("completed", "partial")
        else SessionStatus.FAILED
    )
    return {"success": session.status == SessionStatus.COMPLETED, "observation": observation}


def run_html5_fallback(session: RuntimeSession, html_entry: Path, *, timeout_seconds: int) -> Dict[str, Any]:
    from app.runtime_engines.web.playwright_runner import run_web_game_headless

    shot_dir = session.workspace / "screenshots"
    result = run_web_game_headless(
        html_entry,
        timeout_ms=min(timeout_seconds, 30) * 1000,
        screenshot_dir=shot_dir,
    )
    session.signals.update(result.get("signals") or {})
    session.signals["runtime_method"] = "gamemaker_html5_web_fallback"
    session.screenshot_paths = [Path(p) for p in result.get("screenshots") or []]
    session.metrics.frame_delta_score = float((result.get("signals") or {}).get("frame_delta_score") or 0.0)
    session.metrics.freeze_detected = bool((result.get("signals") or {}).get("freeze_detected"))
    session.metrics.input_responsive = session.metrics.frame_delta_score > 0.02

    if result.get("success"):
        session.status = SessionStatus.COMPLETED
    elif result.get("method") == "static_only":
        session.status = SessionStatus.COMPLETED
    else:
        session.status = SessionStatus.FAILED
        if result.get("error"):
            session.errors.append(str(result["error"]))

    return result
