"""Run Scratch project in scratch-vm (Node.js) — record vars, events, outputs."""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.runtime.scratch.vm")

_RUNNER_SCRIPT = Path(__file__).resolve().parent / "scripts" / "run_scratch_vm.mjs"


def _find_node() -> Optional[str]:
    return shutil.which("node") or shutil.which("nodejs")


def run_scratch_vm(
    sb3_path: Path,
    *,
    timeout_seconds: int = 30,
    max_steps: int = 800,
) -> Dict[str, Any]:
    """
    Execute .sb3 in scratch-vm when Node + runner script dependencies exist.
    Falls back to graph-only mode otherwise.
    """
    node = _find_node()
    if not node or not _RUNNER_SCRIPT.is_file():
        return {
            "success": False,
            "method": "static_graph_only",
            "error": "scratch_vm_unavailable",
            "note": "Install Node.js and npm install in app/runtime_engines/scratch/scripts",
        }

    if not sb3_path.is_file():
        return {"success": False, "method": "none", "error": "sb3_missing"}

    scripts_dir = _RUNNER_SCRIPT.parent
    try:
        proc = subprocess.run(
            [
                node,
                str(_RUNNER_SCRIPT),
                str(sb3_path.resolve()),
                str(max_steps),
            ],
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
            cwd=str(scripts_dir),
            env={**os.environ, "NODE_PATH": str(scripts_dir / "node_modules")},
        )
    except subprocess.TimeoutExpired:
        return {"success": False, "method": "scratch_vm", "error": "vm_timeout"}
    except OSError as exc:
        return {"success": False, "method": "scratch_vm", "error": str(exc)}

    stdout = (proc.stdout or "").strip()
    if proc.returncode != 0:
        return {
            "success": False,
            "method": "scratch_vm",
            "error": "vm_failed",
            "stderr_tail": (proc.stderr or "")[-500:],
            "stdout_tail": stdout[-500:],
        }

    try:
        payload = json.loads(stdout.splitlines()[-1] if stdout else "{}")
    except json.JSONDecodeError:
        return {
            "success": False,
            "method": "scratch_vm",
            "error": "invalid_vm_json",
            "stdout_tail": stdout[-500:],
        }

    payload["success"] = bool(payload.get("ran"))
    payload["method"] = "scratch_vm"
    return payload
