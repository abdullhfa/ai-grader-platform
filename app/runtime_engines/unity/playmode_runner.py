"""Unity Play Mode test runner via batchmode."""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict

from app.runtime_engines.unity.build_runner import resolve_unity_binary
from app.runtime_engines.unity.log_parser import parse_unity_editor_log


@dataclass
class UnityPlayModeConfig:
    project_path: Path
    unity_path: Path
    results_path: Path
    log_path: Path
    timeout_seconds: int = 900


def run_unity_playmode_tests(cfg: UnityPlayModeConfig) -> Dict[str, Any]:
    cfg.results_path.parent.mkdir(parents=True, exist_ok=True)
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(cfg.unity_path),
        "-batchmode",
        "-nographics",
        "-projectPath",
        str(cfg.project_path),
        "-runTests",
        "-testPlatform",
        "playmode",
        "-testResults",
        str(cfg.results_path),
        "-logFile",
        str(cfg.log_path),
        "-quit",
    ]

    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=cfg.timeout_seconds,
            cwd=str(cfg.project_path),
        )
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "error": "unity_playmode_timeout",
            "command": cmd,
            "method": "unity_playmode_tests",
        }
    except OSError as exc:
        return {
            "success": False,
            "error": str(exc),
            "command": cmd,
            "method": "unity_playmode_tests",
        }

    log_text = ""
    if cfg.log_path.is_file():
        try:
            log_text = cfg.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = proc.stdout or proc.stderr or ""

    parsed = parse_unity_editor_log(log_text)
    results_found = cfg.results_path.is_file()

    return {
        "success": proc.returncode == 0 and results_found,
        "exit_code": proc.returncode,
        "results_path": str(cfg.results_path) if results_found else None,
        "log_path": str(cfg.log_path),
        "log_analysis": parsed,
        "method": "unity_playmode_tests",
    }


def maybe_run_playmode_tests(project_path: Path, workspace: Path, *, timeout_seconds: int = 600) -> Dict[str, Any]:
    unity_bin = resolve_unity_binary()
    if not unity_bin:
        return {
            "success": False,
            "skipped": True,
            "reason": "unity_binary_not_configured",
            "hint": "Set AI_GRADER_UNITY_BIN to Unity.exe",
        }

    tests_dir = project_path / "Assets" / "Tests"
    if not tests_dir.is_dir():
        return {
            "success": False,
            "skipped": True,
            "reason": "no_tests_folder",
        }

    return run_unity_playmode_tests(
        UnityPlayModeConfig(
            project_path=project_path,
            unity_path=unity_bin,
            results_path=workspace / "playmode_results.xml",
            log_path=workspace / "playmode_editor.log",
            timeout_seconds=timeout_seconds,
        )
    )
