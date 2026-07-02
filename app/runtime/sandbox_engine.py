"""
Unified Runtime Sandbox Engine — secure isolated execution for multi-platform artifacts.

Wraps runtime_observation_sandbox with production config, platform routing, and failure handling.
"""
from __future__ import annotations

import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Sequence

from app.core.logging_setup import log_structured
from app.core.production_config import get_production_config
from app.governance_freeze_registry import is_l4_sandbox_permitted

logger = logging.getLogger("ai_grader.runtime.sandbox")

PLATFORM_UNITY = "unity"
PLATFORM_GODOT = "godot"
PLATFORM_PYTHON = "python"
PLATFORM_WEB = "web"
PLATFORM_APK = "apk"
PLATFORM_PCK = "pck"
PLATFORM_EXE = "generic_exe"
PLATFORM_UNKNOWN = "unknown"


def detect_platform(path: Path) -> str:
    ext = path.suffix.lower()
    name = path.name.lower()
    if ext == ".apk":
        return PLATFORM_APK
    if ext == ".pck":
        return PLATFORM_PCK
    if ext == ".py":
        return PLATFORM_PYTHON
    if ext in (".html", ".htm"):
        return PLATFORM_WEB
    if ext == ".exe":
        try:
            from app.runtime_observation_sandbox import detect_unity_build_for_exe

            if detect_unity_build_for_exe(path).get("detected"):
                return PLATFORM_UNITY
        except Exception:
            pass
        if (path.parent / "project.godot").is_file() or name.endswith(".exe"):
            if (path.parent / "project.godot").is_file():
                return PLATFORM_GODOT
        return PLATFORM_EXE
    return PLATFORM_UNKNOWN


def _validate_python_script(path: Path, timeout: int) -> Dict[str, Any]:
    """Syntax-check + short dry-run import (no network)."""
    started = time.monotonic()
    result: Dict[str, Any] = {
        "platform": PLATFORM_PYTHON,
        "path": str(path),
        "status": "failed",
        "signals": {},
    }
    try:
        proc = subprocess.run(
            [sys.executable, "-m", "py_compile", str(path)],
            capture_output=True,
            text=True,
            timeout=min(timeout, 8),
            cwd=str(path.parent),
        )
        result["exit_code"] = proc.returncode
        result["stderr_tail"] = (proc.stderr or "")[-500:]
        if proc.returncode == 0:
            result["status"] = "completed"
            result["signals"] = {"syntax_valid": True, "crash_detected": False}
        else:
            result["signals"] = {"syntax_valid": False, "crash_detected": True}
    except subprocess.TimeoutExpired:
        result["status"] = "timeout"
        result["signals"] = {"syntax_valid": False, "timeout": True}
    except Exception as exc:
        result["status"] = "error"
        result["error"] = str(exc)
    result["duration_ms"] = int((time.monotonic() - started) * 1000)
    return result


def _validate_web_project(path: Path) -> Dict[str, Any]:
    """Static validation for HTML/JS entry points."""
    content = ""
    try:
        content = path.read_text(encoding="utf-8", errors="replace")[:50000]
    except OSError as exc:
        return {"platform": PLATFORM_WEB, "path": str(path), "status": "error", "error": str(exc)}
    has_script = "<script" in content.lower()
    has_canvas = "<canvas" in content.lower()
    return {
        "platform": PLATFORM_WEB,
        "path": str(path),
        "status": "completed",
        "signals": {
            "html_valid": bool(content.strip()),
            "has_script": has_script,
            "has_canvas": has_canvas,
            "interactive_hint": has_script or has_canvas,
        },
    }


def collect_runnable_artifacts(paths: Sequence[str]) -> List[Dict[str, Any]]:
    cfg = get_production_config()
    artifacts: List[Dict[str, Any]] = []
    for raw in paths or []:
        p = Path(raw)
        if not p.is_file():
            continue
        if p.suffix.lower() not in cfg.allowed_sandbox_extensions:
            continue
        if "unitycrashhandler" in p.name.lower():
            continue
        artifacts.append(
            {
                "path": str(p.resolve()),
                "name": p.name,
                "platform": detect_platform(p),
                "size_bytes": p.stat().st_size,
            }
        )
    return artifacts[: cfg.sandbox_max_artifacts]


def _run_web_headless(
    path: Path,
    cfg: Any,
    submission_key: str,
    *,
    enable_browser_automation: bool = False,
) -> Dict[str, Any]:
    """Headless web runtime — PRO browser automation or legacy game runner."""
    shot_dir = Path(f"uploads/runtime_sessions/{submission_key}/screenshots")
    root = path.parent if path.is_file() else path

    if enable_browser_automation:
        from app.runtime_engines.web.browser_automation import run_web_browser_automation

        result = run_web_browser_automation(
            root,
            path if path.is_file() else None,
            timeout_ms=cfg.sandbox_timeout_seconds * 1000,
            screenshot_dir=shot_dir,
        )
    else:
        from app.runtime_engines.web.playwright_runner import run_web_game_headless

        result = run_web_game_headless(
            path,
            timeout_ms=cfg.sandbox_timeout_seconds * 1000,
            screenshot_dir=shot_dir,
        )

    status = "completed" if result.get("success") or result.get("method") == "static_only" else "failed"
    signals = dict(result.get("signals") or {})
    signals["runtime_method"] = result.get("method")
    if result.get("navigation_steps"):
        signals["navigation_steps"] = result["navigation_steps"]
    if result.get("web_browser_automation"):
        signals["web_browser_automation"] = result["web_browser_automation"]
    payload = {
        "platform": PLATFORM_WEB,
        "path": str(path),
        "status": status,
        "signals": signals,
        "screenshots": result.get("screenshots") or [],
        "runtime_method": result.get("method"),
        "console_errors": result.get("console_errors") or [],
        "page_errors": result.get("page_errors") or [],
        "http_errors": result.get("http_errors") or [],
        "navigation_steps": result.get("navigation_steps") or [],
        "web_browser_automation": result.get("web_browser_automation"),
    }
    if enable_browser_automation:
        payload["observation_mode"] = "pro_web_browser_automation"
    return payload


def _run_android_mobile(
    path: Path,
    cfg: Any,
    submission_key: str,
    *,
    enable_emulator_automation: bool = False,
) -> Dict[str, Any]:
    """PRO Android Emulator Farm — Appium/adb UI scenarios."""
    shot_dir = Path(f"uploads/runtime_sessions/{submission_key}/android")
    root = path.parent if path.is_file() else path

    if not enable_emulator_automation:
        from app.runtime_observation_sandbox import analyze_apk
        from app.runtime_engines.android.project_probe import detect_project_stack

        if path.suffix.lower() in {".apk", ".aab"}:
            static = analyze_apk(path)
        else:
            probe = detect_project_stack(path)
            static = {
                "valid": probe.get("platform_type") not in ("none", None),
                "signals": {"android_project_detected": probe.get("platform_type") != "none"},
            }
        return {
            "platform": PLATFORM_APK,
            "path": str(path),
            "status": "completed" if static.get("valid") else "failed",
            "signals": static.get("signals") or {},
            "runtime_method": "static_apk_only",
        }

    from app.runtime_engines.android.mobile_automation import run_android_mobile_automation

    result = run_android_mobile_automation(
        root,
        apk_path=path if path.suffix.lower() in {".apk", ".aab"} else None,
        timeout_seconds=cfg.sandbox_timeout_seconds,
        screenshot_dir=shot_dir,
    )
    status = "completed" if result.get("success") or result.get("method") == "static_only" else "failed"
    signals = dict(result.get("signals") or {})
    signals["runtime_method"] = result.get("method")
    if result.get("ui_steps"):
        signals["ui_steps"] = result["ui_steps"]
    if result.get("android_mobile_automation"):
        signals["android_mobile_automation"] = result["android_mobile_automation"]
    return {
        "platform": PLATFORM_APK,
        "path": str(path),
        "status": status,
        "signals": signals,
        "screenshots": result.get("screenshots") or [],
        "screen_recordings": result.get("screen_recordings") or [],
        "runtime_method": result.get("method"),
        "console_errors": result.get("console_errors") or [],
        "ui_steps": result.get("ui_steps") or [],
        "android_mobile_automation": result.get("android_mobile_automation"),
        "observation_mode": "pro_android_emulator_automation",
    }


def run_sandbox_observation(
    submission_paths: Sequence[str],
    *,
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    student_name: str = "",
    enable_smoke_test: bool = True,
    enable_web_browser_automation: bool = False,
    enable_android_emulator_automation: bool = False,
    enable_gamemaker_runtime_verification: bool = False,
    enable_scratch_runtime_verification: bool = False,
    grading_mode: str | None = None,
) -> Dict[str, Any]:
    """
    Production sandbox entry — orchestrator-first with legacy fallback.
    """
    cfg = get_production_config()
    if not cfg.enable_l4_sandbox or not is_l4_sandbox_permitted():
        return {
            "status": "gated",
            "reason": "L4_sandbox_not_permitted",
            "observation_mode": "gated_stub",
            "platform_analyses": [],
        }

    submission_key = student_name or f"submission_{submission_id or 'unknown'}"

    # Phase 1: orchestrated runtime for web/godot/exe roots
    try:
        from app.runtime.orchestrator import run_runtime_observation

        orchestrated = run_runtime_observation(
            submission_paths,
            submission_id=submission_id,
            batch_id=batch_id,
            student_name=student_name,
            enable_smoke_test=enable_smoke_test,
            enable_web_browser_automation=enable_web_browser_automation,
            enable_android_emulator_automation=enable_android_emulator_automation,
            enable_gamemaker_runtime_verification=enable_gamemaker_runtime_verification,
            enable_scratch_runtime_verification=enable_scratch_runtime_verification,
            grading_mode=grading_mode,
        )
        if orchestrated.get("status") not in ("skipped",) or orchestrated.get("engine"):
            orchestrated["artifact_count"] = len(collect_runnable_artifacts(submission_paths))
            return orchestrated
    except Exception:
        logger.exception("Orchestrator path failed — falling back to legacy sandbox")

    artifacts = collect_runnable_artifacts(submission_paths)
    if not artifacts:
        return {
            "status": "skipped",
            "reason": "no_runnable_artifacts",
            "platform_analyses": [],
        }

    platform_analyses: List[Dict[str, Any]] = []
    for art in artifacts:
        path = Path(art["path"])
        platform = art["platform"]
        try:
            if platform == PLATFORM_PYTHON:
                platform_analyses.append(
                    _validate_python_script(path, cfg.sandbox_timeout_seconds)
                )
            elif platform == PLATFORM_WEB:
                if enable_smoke_test:
                    platform_analyses.append(
                        _run_web_headless(
                            path,
                            cfg,
                            submission_key,
                            enable_browser_automation=enable_web_browser_automation,
                        )
                    )
                else:
                    platform_analyses.append(_validate_web_project(path))
            elif platform == PLATFORM_APK:
                platform_analyses.append(
                    _run_android_mobile(
                        path,
                        cfg,
                        submission_key,
                        enable_emulator_automation=enable_android_emulator_automation,
                    )
                )
            else:
                platform_analyses.append(
                    {"platform": platform, "path": str(path), "status": "delegated"}
                )
        except Exception as exc:
            platform_analyses.append(
                {
                    "platform": platform,
                    "path": str(path),
                    "status": "error",
                    "error": str(exc),
                }
            )

    if enable_android_emulator_automation and not any(
        r.get("platform") == PLATFORM_APK for r in platform_analyses
    ):
        try:
            from app.runtime.orchestrator import infer_submission_root
            from app.runtime_engines.android.project_probe import submission_has_android_artifacts

            _root = infer_submission_root(submission_paths, student_name=student_name)
            if _root and submission_has_android_artifacts(_root):
                platform_analyses.append(
                    _run_android_mobile(
                        _root,
                        cfg,
                        submission_key,
                        enable_emulator_automation=True,
                    )
                )
        except Exception as exc:
            platform_analyses.append(
                {
                    "platform": PLATFORM_APK,
                    "status": "error",
                    "error": str(exc),
                }
            )

    heavy_paths = [
        a["path"]
        for a in artifacts
        if a["platform"]
        in (PLATFORM_UNITY, PLATFORM_PCK, PLATFORM_EXE, PLATFORM_GODOT)
        or (
            a["platform"] == PLATFORM_APK
            and not enable_android_emulator_automation
        )
    ]
    observation: Dict[str, Any] = {}
    if heavy_paths and enable_smoke_test:
        try:
            from app.runtime_observation_sandbox import observe_runtime_artifacts

            observation = observe_runtime_artifacts(
                heavy_paths,
                enable_smoke_test=True,
                submission_id=submission_id,
                batch_id=batch_id,
                student_name=student_name,
                grading_mode=grading_mode,
            )
        except Exception as exc:
            logger.exception("L4 observation failed")
            observation = {
                "status": "error",
                "error": str(exc),
                "observation_mode": "controlled_static_and_smoke",
            }

    web_shots: List[Dict[str, Any]] = []
    android_shots: List[Dict[str, Any]] = []
    for row in platform_analyses:
        if row.get("platform") == PLATFORM_WEB:
            for shot in row.get("screenshots") or []:
                web_shots.append({"path": shot, "status": "captured", "source": "web_headless"})
        if row.get("platform") == PLATFORM_APK:
            for shot in row.get("screenshots") or []:
                android_shots.append({"path": shot, "status": "captured", "source": "android_emulator"})
            for rec in row.get("screen_recordings") or []:
                android_shots.append({"path": rec, "status": "captured", "source": "android_screen_record"})

    if not observation:
        observation = {
            "status": "completed" if platform_analyses else "skipped",
            "observation_mode": "platform_static_only",
        }

    if web_shots and not observation.get("runtime_screenshots"):
        observation["runtime_screenshots"] = web_shots
        observation["runtime_observed"] = True
    if android_shots:
        existing = list(observation.get("runtime_screenshots") or [])
        observation["runtime_screenshots"] = existing + android_shots
        observation["runtime_observed"] = True

    observation["platform_analyses"] = platform_analyses
    observation["sandbox_engine_version"] = "2.0"
    observation["artifact_count"] = len(artifacts)

    log_structured(
        "sandbox_observation_complete",
        submission_id=submission_id,
        status=observation.get("status"),
        artifact_count=len(artifacts),
    )
    return observation
