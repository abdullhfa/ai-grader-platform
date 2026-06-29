"""Runtime process watchdog — timeout and stuck process termination."""
from __future__ import annotations

import os
import subprocess
import time
from typing import Any, Dict, Optional


def terminate_process_tree(proc: Optional[subprocess.Popen], *, grace_seconds: float = 2.0) -> Dict[str, Any]:
    """Best-effort terminate a subprocess and its children (Windows-friendly)."""
    if not proc or proc.poll() is not None:
        return {"terminated": False, "reason": "not_running"}

    pid = proc.pid
    try:
        proc.terminate()
        deadline = time.time() + grace_seconds
        while time.time() < deadline:
            if proc.poll() is not None:
                return {"terminated": True, "method": "terminate", "pid": pid}
            time.sleep(0.1)
        proc.kill()
        return {"terminated": True, "method": "kill", "pid": pid}
    except OSError as exc:
        if os.name == "nt" and pid:
            try:
                subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    timeout=10,
                )
                return {"terminated": True, "method": "taskkill", "pid": pid}
            except Exception:
                pass
        return {"terminated": False, "error": str(exc), "pid": pid}


def run_with_watchdog(
    cmd: list[str],
    *,
    timeout_seconds: int,
    cwd: Optional[str] = None,
) -> Dict[str, Any]:
    """Run command with hard timeout — kills stuck processes."""
    try:
        proc = subprocess.Popen(cmd, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = proc.communicate(timeout=timeout_seconds)
            return {
                "success": proc.returncode == 0,
                "exit_code": proc.returncode,
                "stdout_tail": (stdout or "")[-2000:],
                "stderr_tail": (stderr or "")[-2000:],
                "watchdog": "completed",
            }
        except subprocess.TimeoutExpired:
            kill_result = terminate_process_tree(proc)
            return {
                "success": False,
                "error": "watchdog_timeout",
                "timeout_seconds": timeout_seconds,
                "watchdog_kill": kill_result,
            }
    except OSError as exc:
        return {"success": False, "error": str(exc), "command": cmd}
