"""Unity input automation driver — Sprint 2.5."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.runtime_engines.base import RuntimeSession


def run_input_burst(session: RuntimeSession) -> Dict[str, Any]:
    """
    Execute bounded WASD/Space/Enter/mouse burst via existing L4 interaction trace.
    Falls back to optional pyautogui when configured.
    """
    session.events.record("input_burst_started", source="input_driver")

    try:
        from app.runtime_interaction_trace import run_interaction_burst

        burst = run_interaction_burst()
        session.events.record(
            "input_burst_completed",
            source="input_driver",
            status=burst.get("status"),
            keys_sent=burst.get("keys_sent"),
        )
        return burst
    except Exception as exc:
        session.events.record(
            "input_burst_failed",
            source="input_driver",
            severity="warning",
            error=str(exc),
        )

    try:
        import pyautogui  # type: ignore

        for key in ("w", "a", "s", "d", "space", "enter"):
            pyautogui.press(key)
        pyautogui.click()
        result = {"status": "completed", "method": "pyautogui", "keys_sent": 6}
        session.events.record("input_burst_completed", source="pyautogui", **result)
        return result
    except Exception:
        return {"status": "skipped", "reason": "input_driver_unavailable"}


def extract_input_trace(observation: Dict[str, Any]) -> Dict[str, Any]:
    trace = observation.get("interaction_trace")
    if isinstance(trace, dict):
        return trace
    unity_obs = observation.get("unity_observation") or {}
    nested = unity_obs.get("interaction_trace")
    return nested if isinstance(nested, dict) else {}
