"""Runtime validation engine — smoke, freeze, soft-lock, functional signals."""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger("ai_grader.runtime.validation")

VALIDATION_VERSION = "runtime_validation_v1"


def _signal_graph(obs: Dict[str, Any]) -> Dict[str, Any]:
    return obs.get("runtime_signal_graph") or {}


def detect_freeze(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Detect likely freeze: process ran but no input/visual response."""
    signals = _signal_graph(obs).get("signals") or {}
    duration = float(obs.get("runtime_duration_seconds") or 0)
    visual = signals.get("visual_response_to_input", "none")
    input_det = signals.get("input_detected", "none")
    frozen = (
        obs.get("status") == "completed"
        and duration >= 8
        and visual in ("none", "unknown")
        and input_det in ("none", "unknown")
    )
    return {
        "freeze_suspected": frozen,
        "duration_seconds": duration,
        "visual_response": visual,
        "input_detected": input_det,
    }


def detect_soft_lock(obs: Dict[str, Any]) -> Dict[str, Any]:
    """Soft-lock: launch ok but black screen or no scene progression."""
    shots = obs.get("runtime_screenshots") or []
    black_count = sum(
        1
        for s in shots
        if isinstance(s, dict)
        and (
            s.get("visual_state") == "black_screen"
            or (s.get("visual_stats") or {}).get("black_screen_possible")
        )
    )
    unity = obs.get("unity_observation_summary") or []
    scene_loaded = any(
        isinstance(u, dict) and u.get("scene_loaded_hint") for u in unity
    )
    soft_lock = black_count >= 2 and not scene_loaded
    return {
        "soft_lock_suspected": soft_lock,
        "black_screenshot_count": black_count,
        "scene_loaded_hint": scene_loaded,
    }


def detect_crash(obs: Dict[str, Any]) -> Dict[str, Any]:
    crashed = bool(obs.get("crash_detected") or obs.get("process_crashed"))
    exit_code = obs.get("exit_code")
    if exit_code is not None and int(exit_code) != 0:
        crashed = True
    for analysis in obs.get("platform_analyses") or []:
        if isinstance(analysis, dict) and analysis.get("signals", {}).get("crash_detected"):
            crashed = True
    return {"crash_detected": crashed, "exit_code": exit_code}


def _runtime_method(obs: Dict[str, Any]) -> str:
    method = str(obs.get("observation_mode") or "")
    if not method and obs.get("platform_analyses"):
        sig = (obs["platform_analyses"][0] or {}).get("signals") or {}
        method = str(sig.get("runtime_method") or "")
    return method


def functional_smoke_pass(obs: Dict[str, Any]) -> Dict[str, Any]:
    method = _runtime_method(obs)
    if method in ("godot_static_analysis", "godot_apk_pck_static_scan"):
        return {
            "functional_smoke_pass": False,
            "reason": "structure_only_no_game_launch",
            "runtime_method": method,
        }
    if obs.get("game_launch_attempted") is False:
        return {
            "functional_smoke_pass": False,
            "reason": "game_not_launched",
            "runtime_method": method,
        }

    godot_state = obs.get("godot_state_validation") or (obs.get("signals") or {}).get(
        "godot_state_validation"
    )
    if isinstance(godot_state, dict) and godot_state.get("method"):
        if not godot_state.get("state_ok"):
            return {
                "functional_smoke_pass": False,
                "reason": "godot_state_validation_failed",
                **godot_state,
            }

    shots = obs.get("runtime_screenshots") or []
    if shots and isinstance(godot_state, dict):
        black = sum(
            1
            for s in shots
            if isinstance(s, dict)
            and (
                s.get("visual_state") == "black_screen"
                or (s.get("visual_stats") or {}).get("black_screen_possible")
            )
        )
        if black >= max(1, len(shots) // 2):
            return {
                "functional_smoke_pass": False,
                "reason": "screenshot_black_screen",
                "black_screenshot_count": black,
            }

    crash = detect_crash(obs)
    if crash["crash_detected"]:
        return {"functional_smoke_pass": False, "reason": "crash", **crash}
    freeze = detect_freeze(obs)
    if freeze["freeze_suspected"]:
        return {"functional_smoke_pass": False, "reason": "freeze_suspected", **freeze}
    soft = detect_soft_lock(obs)
    if soft["soft_lock_suspected"]:
        return {"functional_smoke_pass": False, "reason": "soft_lock", **soft}
    if obs.get("runtime_verified") is True and (
        obs.get("runtime_screenshots")
        or float(obs.get("runtime_duration_seconds") or 0) > 1.0
    ):
        return {"functional_smoke_pass": True, "reason": "runtime_verified_with_evidence"}

    pck_smoke = (obs.get("pck_smoke") or (obs.get("signals") or {}).get("pck_smoke")) or {}
    if isinstance(pck_smoke, dict) and pck_smoke.get("success"):
        return {"functional_smoke_pass": True, "reason": "godot_main_pack_smoke"}

    for analysis in obs.get("artifact_analyses") or []:
        if not isinstance(analysis, dict):
            continue
        if analysis.get("smoke_result") in ("stable_window", "launch_ok"):
            return {"functional_smoke_pass": True, "reason": "artifact_smoke_ok"}

    status = obs.get("status")
    if status in ("completed",) and (
        obs.get("runtime_verified") or obs.get("runtime_observed")
    ):
        return {
            "functional_smoke_pass": False,
            "reason": "completed_without_launch_evidence",
        }
    if status in ("completed", "partial"):
        return {"functional_smoke_pass": False, "reason": f"status_{status}_no_smoke"}
    if status == "gated":
        return {"functional_smoke_pass": None, "reason": "gated"}
    return {"functional_smoke_pass": False, "reason": f"status_{status}"}


def validate_runtime_observation(obs: Optional[Dict[str, Any]]) -> Dict[str, Any]:
    """Full runtime validation report attached to inventory."""
    started = time.monotonic()
    obs = obs or {}
    smoke = functional_smoke_pass(obs)
    report = {
        "validation_version": VALIDATION_VERSION,
        "status": obs.get("status"),
        "functional_smoke": smoke,
        "freeze_analysis": detect_freeze(obs),
        "soft_lock_analysis": detect_soft_lock(obs),
        "crash_analysis": detect_crash(obs),
        "gameplay_verification": {
            "mechanics_observed": bool(
                (_signal_graph(obs).get("signals") or {}).get("mechanics_hint")
                or obs.get("runtime_observed")
            ),
            "ui_interaction_hint": (_signal_graph(obs).get("signals") or {}).get(
                "visual_response_to_input"
            ),
            "advisory_only": True,
        },
        "duration_ms": int((time.monotonic() - started) * 1000),
    }
    logger.info(
        "runtime_validation status=%s smoke=%s",
        report.get("status"),
        smoke.get("functional_smoke_pass"),
    )
    return report
