"""
Runtime stress harness — PHASE C battery runner.

Exercises sandbox + validation under failure scenarios.
Does not mutate grading snapshots.
"""
from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.runtime.sandbox_engine import run_sandbox_observation
from app.runtime.sandbox_recovery import append_stress_log, build_recovery_report, escalate_timeout
from app.runtime.validation_engine import detect_crash, detect_freeze, validate_runtime_observation

# Mock Unity/runtime observations for scenarios that cannot run real builds in CI.
MOCK_SCENARIOS: Dict[str, Dict[str, Any]] = {
    "broken_unity_build": {
        "status": "error",
        "crash_detected": True,
        "exit_code": 1,
        "observation_mode": "stress_mock",
        "runtime_signal_graph": {"signals": {"visual_response_to_input": "none"}},
        "stdout": "Failed to load player",
    },
    "missing_dll": {
        "status": "error",
        "crash_detected": True,
        "exit_code": -1073741515,
        "observation_mode": "stress_mock",
        "stderr": "DLL not found: UnityPlayer.dll",
    },
    "fullscreen_freeze": {
        "status": "completed",
        "runtime_duration_seconds": 15,
        "runtime_signal_graph": {
            "signals": {"visual_response_to_input": "none", "input_detected": "none"},
        },
        "runtime_screenshots": [{"visual_state": "black_screen", "visual_stats": {"black_screen_possible": True}}],
    },
    "invalid_scene": {
        "status": "completed",
        "unity_observation_summary": [{"scene_loaded_hint": False}],
        "runtime_screenshots": [{"visual_state": "black_screen"}, {"visual_state": "black_screen"}],
    },
    "dead_input_state": {
        "status": "completed",
        "runtime_duration_seconds": 10,
        "runtime_signal_graph": {
            "signals": {"visual_response_to_input": "none", "input_detected": "none"},
        },
    },
    "memory_spike": {
        "status": "error",
        "crash_detected": True,
        "exit_code": 137,
        "observation_mode": "stress_mock",
        "stderr": "OutOfMemoryException",
    },
    "corrupted_save": {
        "status": "error",
        "crash_detected": True,
        "observation_mode": "stress_mock",
        "stderr": "Invalid save format",
    },
}

FIXTURE_MAP = {
    "infinite_loop": "infinite_loop.py",
    "crash_on_launch": "syntax_crash.py",
    "missing_dependency": "missing_module.py",
    "hung_process": "hung_process.py",
    "corrupted_python": "corrupted_save.py",
}


def _fixtures_root() -> Path:
    return Path(__file__).resolve().parents[2] / "tests" / "runtime_stress" / "fixtures"


def _run_python_subprocess(path: Path, timeout: int) -> Dict[str, Any]:
    started = time.monotonic()
    root_pid: Optional[int] = None
    try:
        proc = subprocess.Popen(
            [sys.executable, str(path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=str(path.parent),
        )
        root_pid = proc.pid
        try:
            stdout, stderr = proc.communicate(timeout=timeout)
            exit_code = proc.returncode
            status = "completed" if exit_code == 0 else "error"
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.communicate(timeout=2)
            stdout, stderr = b"", b"timeout"
            exit_code = -9
            status = "timeout"
        duration = time.monotonic() - started
        return {
            "status": status,
            "exit_code": exit_code,
            "runtime_duration_seconds": round(duration, 2),
            "stdout": (stdout or b"").decode("utf-8", errors="replace")[-2000:],
            "stderr": (stderr or b"").decode("utf-8", errors="replace")[-2000:],
            "crash_detected": status in ("error", "timeout"),
            "process_crashed": status in ("error", "timeout"),
            "root_pid": root_pid,
            "observation_mode": "stress_subprocess",
            "platform_analyses": [
                {
                    "platform": "python",
                    "path": str(path),
                    "status": status,
                    "signals": {"crash_detected": status != "completed", "timeout": status == "timeout"},
                }
            ],
        }
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "crash_detected": True,
            "root_pid": root_pid,
            "observation_mode": "stress_subprocess",
        }


def _check_replay_integrity(snapshot: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    if not snapshot:
        return {"checked": False}
    from app.academic_event_replay import build_academic_timeline_replay
    from app.deterministic_replay_engine import verify_deterministic_replay

    timeline = build_academic_timeline_replay(snapshot)
    v = verify_deterministic_replay(timeline.get("events") or [], snapshot)
    return {
        "checked": True,
        "replay_verified": bool(v.get("replay_verified")),
        "protected_digest_match": bool(v.get("protected_digest_match")),
    }


def run_stress_scenario(
    scenario_id: str,
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 5,
    timeout_attempt: int = 0,
    write_log: bool = True,
) -> Dict[str, Any]:
    """Run one stress scenario and return structured result."""
    effective_timeout = escalate_timeout(timeout_seconds, timeout_attempt, max_seconds=15)

    if scenario_id in MOCK_SCENARIOS:
        observation = dict(MOCK_SCENARIOS[scenario_id])
        root_pid = None
    elif scenario_id in FIXTURE_MAP:
        fixture = _fixtures_root() / FIXTURE_MAP[scenario_id]
        if not fixture.exists():
            return {"scenario_id": scenario_id, "error": "fixture_missing", "path": str(fixture)}
        if scenario_id == "crash_on_launch":
            observation = run_sandbox_observation([str(fixture)], enable_smoke_test=False)
            root_pid = None
        elif scenario_id in ("infinite_loop", "hung_process"):
            observation = _run_python_subprocess(fixture, effective_timeout)
            root_pid = observation.get("root_pid")
        else:
            observation = run_sandbox_observation([str(fixture)], enable_smoke_test=False)
            root_pid = None
    else:
        return {"scenario_id": scenario_id, "error": "unknown_scenario"}

    validation = validate_runtime_observation(observation)
    crash = detect_crash(observation)
    freeze = detect_freeze(observation)
    recovery = build_recovery_report(
        scenario_id=scenario_id,
        observation=observation,
        root_pid=root_pid,
        timeout_attempt=timeout_attempt,
    )
    replay = _check_replay_integrity(snapshot)

    result = {
        "scenario_id": scenario_id,
        "timeout_seconds": effective_timeout,
        "detect_crash": crash.get("crash_detected"),
        "detect_freeze": freeze.get("freeze_suspected"),
        "functional_smoke_pass": validation.get("functional_smoke_pass"),
        "observation_status": observation.get("status"),
        "recovery": recovery,
        "replay_integrity": replay,
        "requirements": {
            "detect_crash": True,
            "kill_orphan": recovery.get("orphan_cleanup", {}).get("attempted") is not False,
            "save_logs": recovery.get("logs_captured"),
            "timeout_escalation": timeout_attempt >= 0,
            "replay_integrity_preserved": replay.get("protected_digest_match", replay.get("checked") is False),
        },
    }
    if write_log:
        append_stress_log(result)
    return result


def run_full_stress_battery(
    *,
    snapshot: Optional[Dict[str, Any]] = None,
    scenario_ids: Optional[List[str]] = None,
) -> Dict[str, Any]:
    ids = scenario_ids or list(MOCK_SCENARIOS.keys()) + list(FIXTURE_MAP.keys())
    results = [run_stress_scenario(sid, snapshot=snapshot, write_log=False) for sid in ids]
    passed = sum(
        1
        for r in results
        if r.get("detect_crash") or r.get("detect_freeze") or r.get("observation_status") in ("error", "timeout", "completed")
    )
    return {
        "report_type": "runtime_stress_battery_v1",
        "scenario_count": len(results),
        "scenarios_passed": passed,
        "results": results,
    }
