"""Unity headless Windows build runner."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from app.runtime.process_watchdog import run_with_watchdog
from app.runtime_engines.unity.hardening import analyze_unity_static_project, validate_unity_manifest
from app.runtime_engines.unity.log_parser import parse_unity_editor_log


@dataclass
class UnityBuildConfig:
    project_path: Path
    unity_path: Path
    output_exe: Path
    log_path: Path
    timeout_seconds: int = 900


def resolve_unity_binary() -> Optional[Path]:
    env = os.environ.get("AI_GRADER_UNITY_BIN") or os.environ.get("UNITY_BIN")
    if env:
        candidate = Path(env)
        if candidate.is_file():
            return candidate

    if os.name != "nt":
        return None

    hub_root = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Unity" / "Hub" / "Editor"
    if hub_root.is_dir():
        versions = sorted([p for p in hub_root.iterdir() if p.is_dir()], reverse=True)
        for version_dir in versions:
            editor = version_dir / "Editor" / "Unity.exe"
            if editor.is_file():
                return editor
    return None


def run_unity_build(cfg: UnityBuildConfig) -> Dict[str, Any]:
    cfg.output_exe.parent.mkdir(parents=True, exist_ok=True)
    cfg.log_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(cfg.unity_path),
        "-batchmode",
        "-nographics",
        "-quit",
        "-projectPath",
        str(cfg.project_path),
        "-buildWindows64Player",
        str(cfg.output_exe),
        "-logFile",
        str(cfg.log_path),
    ]

    manifest_check = validate_unity_manifest(cfg.project_path)
    result = run_with_watchdog(cmd, timeout_seconds=cfg.timeout_seconds, cwd=str(cfg.project_path))
    if result.get("error") == "watchdog_timeout":
        return {
            "success": False,
            "error": "unity_build_timeout",
            "command": cmd,
            "method": "unity_headless_build",
            "watchdog": result.get("watchdog_kill"),
            "manifest_validation": manifest_check,
            "static_fallback": analyze_unity_static_project(cfg.project_path),
        }
    if not result.get("success") and result.get("error"):
        return {
            "success": False,
            "error": result.get("error"),
            "command": cmd,
            "method": "unity_headless_build",
            "manifest_validation": manifest_check,
            "static_fallback": analyze_unity_static_project(cfg.project_path),
        }

    proc_rc = result.get("exit_code", 1)
    log_text = ""
    if cfg.log_path.is_file():
        try:
            log_text = cfg.log_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            log_text = result.get("stdout_tail") or result.get("stderr_tail") or ""

    parsed = parse_unity_editor_log(log_text)
    artifact_exists = cfg.output_exe.is_file()

    return {
        "success": artifact_exists and proc_rc == 0,
        "exit_code": proc_rc,
        "artifact": str(cfg.output_exe) if artifact_exists else None,
        "log_path": str(cfg.log_path),
        "log_analysis": parsed,
        "stderr_tail": result.get("stderr_tail"),
        "stdout_tail": result.get("stdout_tail"),
        "manifest_validation": manifest_check,
        "method": "unity_headless_build",
        "watchdog": "completed",
    }
