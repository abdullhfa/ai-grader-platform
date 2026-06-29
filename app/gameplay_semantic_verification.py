"""Deterministic gameplay semantic verification (no new AI models)."""
from __future__ import annotations

from typing import Any, Dict, List, Optional


_FAIL_STATE_MARKERS = {
    "death",
    "dead",
    "game_over",
    "lose",
    "restart",
    "respawn",
}
_WIN_STATE_MARKERS = {
    "win",
    "victory",
    "completed",
    "next_level",
    "stage_clear",
}
_LIVES_MARKERS = {
    "lives",
    "health",
    "hp",
    "hearts",
}
_MENU_MARKERS = {
    "menu",
    "main_menu",
    "pause_menu",
    "settings",
    "options",
    "start",
}
_RESTART_MARKERS = {
    "restart",
    "try_again",
    "retry",
    "respawn",
}


def _collect_visual_tokens(observation: Dict[str, Any]) -> List[str]:
    tokens: List[str] = []
    shots = observation.get("runtime_screenshots") or []
    for shot in shots:
        if not isinstance(shot, dict):
            continue
        elements = shot.get("observed_visual_elements") or shot.get("elements") or []
        if isinstance(elements, list):
            for item in elements:
                if item:
                    tokens.append(str(item).strip().lower())
    visual = observation.get("visual_observation_summary") or []
    for row in visual:
        if not isinstance(row, dict):
            continue
        elements = row.get("observed_visual_elements") or []
        if isinstance(elements, list):
            for item in elements:
                if item:
                    tokens.append(str(item).strip().lower())
    return tokens


def _signal_true(signals: Dict[str, Any], key: str) -> bool:
    return signals.get(key) in ("detected", "yes", "observed", True)


def assess_gameplay_semantics(
    observation: Optional[Dict[str, Any]],
    *,
    inventory: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Classify gameplay behavior completeness using runtime heuristics."""
    obs = observation or {}
    inv = inventory or {}
    graph = obs.get("runtime_signal_graph") or {}
    signals = graph.get("signals") or {}

    screenshots = obs.get("runtime_screenshots") or []
    captured = [
        s for s in screenshots if isinstance(s, dict) and s.get("status") == "captured"
    ]
    gameplay_candidate_frames = sum(
        1
        for s in captured
        if str(s.get("visual_state") or "").lower() == "gameplay_candidate"
    )

    moved = signals.get("player_moved") in ("detected", "yes", "observed")
    score_changed = _signal_true(signals, "score_changed")
    timer_progressed = _signal_true(signals, "timer_progressed")
    checkpoint = _signal_true(signals, "progression_checkpoint")
    level_transition = _signal_true(signals, "level_transition")
    collision = _signal_true(signals, "collision_events")
    interaction_detected = bool(
        moved or score_changed or collision or gameplay_candidate_frames >= 1
    )

    visual_tokens = _collect_visual_tokens(obs)
    has_fail_state = any(t in _FAIL_STATE_MARKERS for t in visual_tokens)
    has_win_state = any(t in _WIN_STATE_MARKERS for t in visual_tokens)
    menu_navigation_detected = any(t in _MENU_MARKERS for t in visual_tokens) or _signal_true(
        signals, "menu_navigation"
    )
    restart_flow_detected = any(t in _RESTART_MARKERS for t in visual_tokens) or _signal_true(
        signals, "restart_flow"
    )
    has_lives_system = any(t in _LIVES_MARKERS for t in visual_tokens) or (
        _signal_true(signals, "lives_changed")
        or _signal_true(signals, "health_changed")
    )
    health_or_lives_detected = has_lives_system

    # Progression can be explicit transition, score growth, or structured checkpoint signal.
    score_progression_detected = score_changed or timer_progressed
    progression_detected = level_transition or score_progression_detected or checkpoint
    fail_state_detected = (
        has_fail_state
        or _signal_true(signals, "fail_state")
        or _signal_true(signals, "game_over")
    )

    gameplay_started = bool(
        obs.get("runtime_observed")
        or (inv.get("executable_artifacts") or {}).get("runtime_observed")
        or gameplay_candidate_frames > 0
    )
    gameplay_loop_complete = (
        gameplay_started
        and interaction_detected
        and progression_detected
        and (fail_state_detected or has_win_state)
        and (restart_flow_detected or menu_navigation_detected or has_win_state)
    )
    progression_missing = gameplay_started and interaction_detected and not progression_detected
    loop_incomplete = gameplay_started and not gameplay_loop_complete

    if gameplay_loop_complete:
        verification_level = "L5_verified"
    elif progression_detected or fail_state_detected:
        verification_level = "L5_partial"
    elif interaction_detected:
        verification_level = "L4_plus"
    elif gameplay_started:
        verification_level = "L4"
    else:
        verification_level = "none"

    findings_ar: List[str] = []
    if gameplay_started:
        findings_ar.append("تم تشغيل اللعبة runtime")
    if interaction_detected:
        findings_ar.append("تم رصد تفاعل لعب")
    if menu_navigation_detected:
        findings_ar.append("تم رصد تنقل menu/واجهة")
    if progression_detected:
        findings_ar.append("تم رصد progression/transition")
    else:
        findings_ar.append("لم يُرصد انتقال مستوى/تقدم لعب واضح")
    if score_progression_detected:
        findings_ar.append("تم رصد score/timer progression")
    if fail_state_detected:
        findings_ar.append("تم رصد fail state / game over")
    else:
        findings_ar.append("fail state غير واضح من الملاحظة")
    if restart_flow_detected:
        findings_ar.append("تم رصد restart/respawn flow")
    if not has_lives_system:
        findings_ar.append("نظام الأرواح/الصحة غير ظاهر بالأدلة")
    if loop_incomplete:
        findings_ar.append("حلقة اللعب غير مكتملة وظيفيًا")

    return {
        "version": 1,
        "gameplay_started": gameplay_started,
        "interaction_detected": interaction_detected,
        "progression_detected": progression_detected,
        "fail_state_detected": fail_state_detected,
        "score_progression_detected": score_progression_detected,
        "restart_flow_detected": restart_flow_detected,
        "menu_navigation_detected": menu_navigation_detected,
        "health_or_lives_detected": health_or_lives_detected,
        "lives_or_health_detected": has_lives_system,
        "win_state_detected": has_win_state,
        "gameplay_loop_complete": gameplay_loop_complete,
        "progression_missing": progression_missing,
        "loop_incomplete": loop_incomplete,
        "gameplay_candidate_frames": gameplay_candidate_frames,
        "verification_level": verification_level,
        "findings_ar": findings_ar,
    }

