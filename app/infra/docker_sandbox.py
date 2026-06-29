"""Ephemeral Docker sandbox — isolate runtime execution from host."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.infra.runtime_limits import RuntimeResourceLimits, get_runtime_limits
from app.infra.submission_guard import validate_submission_paths


def docker_sandbox_enabled() -> bool:
    return os.environ.get("AI_GRADER_DOCKER_SANDBOX", "").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


def _docker_available() -> bool:
    return shutil.which("docker") is not None


def _sandbox_image() -> str:
    return os.environ.get(
        "AI_GRADER_SANDBOX_IMAGE",
        "ai-grader/runtime-sandbox:latest",
    )


def run_ephemeral_sandbox(
    command: List[str],
    *,
    workspace: Path,
    mounts: Optional[List[str]] = None,
    limits: Optional[RuntimeResourceLimits] = None,
    env: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Run ``command`` inside a disposable container.

    Falls back to host execution when Docker sandbox is disabled or unavailable.
    """
    guard = validate_submission_paths([str(workspace)])
    if not guard.get("ok"):
        return {"status": "rejected", "guard": guard}

    policy = limits or get_runtime_limits()
    timeout = policy.timeout_seconds

    if not docker_sandbox_enabled() or not _docker_available():
        return {
            "status": "host_fallback",
            "isolation": "none",
            "limits": policy.to_dict(),
            "note": "docker_sandbox_disabled_or_unavailable",
        }

    container_name = f"ai-grader-sandbox-{uuid.uuid4().hex[:12]}"
    workspace = workspace.resolve()
    workspace.mkdir(parents=True, exist_ok=True)

    docker_cmd = [
        "docker",
        "run",
        "--rm",
        "--name",
        container_name,
        *policy.docker_flags(),
        "-v",
        f"{workspace}:/workspace:rw",
        "-w",
        "/workspace",
    ]
    for mount in mounts or []:
        docker_cmd.extend(["-v", mount])
    for key, value in (env or {}).items():
        docker_cmd.extend(["-e", f"{key}={value}"])
    docker_cmd.append(_sandbox_image())
    docker_cmd.extend(command)

    try:
        proc = subprocess.run(
            docker_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "status": "completed" if proc.returncode == 0 else "error",
            "isolation": "docker_ephemeral",
            "container": container_name,
            "returncode": proc.returncode,
            "stdout": (proc.stdout or "")[-8000:],
            "stderr": (proc.stderr or "")[-8000:],
            "limits": policy.to_dict(),
        }
    except subprocess.TimeoutExpired:
        subprocess.run(["docker", "kill", container_name], capture_output=True, check=False)
        return {
            "status": "timeout",
            "isolation": "docker_ephemeral",
            "container": container_name,
            "limits": policy.to_dict(),
        }
    except Exception as exc:
        return {
            "status": "error",
            "isolation": "docker_ephemeral",
            "error": str(exc),
            "limits": policy.to_dict(),
        }


def write_sandbox_manifest(workspace: Path, payload: Dict[str, Any]) -> Path:
    path = workspace / "sandbox_manifest.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
