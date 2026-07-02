"""Mechanics verification facade with explicit L1-L5 levels."""
from __future__ import annotations

from typing import Any, Dict, Optional

from app.gameplay_semantic_verification import assess_gameplay_semantics
from app.gameplay_verifier import _gameplay_verification_blob, _interaction_trace


def verify_mechanics(
    observation: Optional[Dict[str, Any]],
    *,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    obs = observation or {}
    inv = inventory or {}
    sem = assess_gameplay_semantics(obs, inventory=inv)
    trace = _interaction_trace(obs)
    gv = _gameplay_verification_blob(obs, inventory=inv, grading_result=None)
    movement_ok = bool(gv.get("player_movement_verified") or trace.get("player_movement_verified"))
    jump_ok = bool(gv.get("jump_detected") or trace.get("jump_detected") or movement_ok)
    score_ok = bool(gv.get("score_change_detected") or sem.get("score_progression_detected"))
    win_or_lose_ok = bool(sem.get("win_state_detected") or sem.get("fail_state_detected"))
    loop_ok = bool(sem.get("gameplay_loop_complete"))
    l4 = str(gv.get("l4_level") or trace.get("l4_level") or "")

    if loop_ok or l4 == "L4_full":
        level = "L5" if loop_ok else "L4"
    elif l4 in ("L4_full", "L4_partial") or win_or_lose_ok or (score_ok and movement_ok):
        level = "L4"
    elif jump_ok or movement_ok or sem.get("gameplay_started"):
        level = "L3"
    elif obs.get("runtime_observed") or obs.get("runtime_verified"):
        level = "L2"
    else:
        level = "L1"

    return {
        "version": 1,
        "mechanics_level": level,
        "jump_detected": jump_ok,
        "score_system_detected": score_ok,
        "player_movement_detected": movement_ok,
        "win_or_lose_detected": win_or_lose_ok,
        "gameplay_loop_complete": loop_ok,
        "source": "deterministic_semantic_verification",
        "findings_ar": sem.get("findings_ar") or [],
    }
