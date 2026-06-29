"""Sandbox recovery — timeout escalation, orphan cleanup, structured stress logs."""
from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from app.runtime_process_restriction import kill_process_tree


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def escalate_timeout(base_seconds: int, attempt: int, *, max_seconds: int = 60) -> int:
    """Exponential backoff cap for sandbox timeouts."""
    if attempt <= 0:
        return base_seconds
    return min(max_seconds, int(base_seconds * (1.5 ** attempt)))


def cleanup_orphan_process(root_pid: Optional[int]) -> Dict[str, Any]:
    if not root_pid or root_pid <= 0:
        return {"attempted": False, "reason": "no_pid"}
    return kill_process_tree(int(root_pid))


def append_stress_log(entry: Dict[str, Any], log_path: Optional[Path] = None) -> Path:
    path = log_path or Path("uploads/audit/runtime_stress.jsonl")
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {"ts": _utc_now(), **entry}
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return path


def build_recovery_report(
    *,
    scenario_id: str,
    observation: Dict[str, Any],
    root_pid: Optional[int] = None,
    timeout_attempt: int = 0,
) -> Dict[str, Any]:
    cleanup = cleanup_orphan_process(root_pid)
    return {
        "scenario_id": scenario_id,
        "timeout_attempt": timeout_attempt,
        "observation_status": observation.get("status"),
        "orphan_cleanup": cleanup,
        "logs_captured": bool(
            observation.get("stdout")
            or observation.get("stderr")
            or observation.get("logs")
            or observation.get("platform_analyses")
        ),
        "screenshot_count": len(observation.get("runtime_screenshots") or []),
    }
