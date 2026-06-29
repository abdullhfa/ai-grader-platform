"""
Runtime telemetry graph — structured observation timeline (L4 advisory).

Replaces implicit «AI watched gameplay» with governed signal events.
Events do NOT wire to criterion achievement.
"""
from __future__ import annotations

import datetime
from typing import Any, Dict, List, Optional

TELEMETRY_EVENT_TYPES = (
    "process_started",
    "scene_loaded",
    "input_detected",
    "score_changed",
    "collision_detected",
    "level_transition",
    "runtime_duration",
    "crash_state",
)

GRAPH_VERSION = "runtime_telemetry_graph_v1"


def _utc_now() -> str:
    return datetime.datetime.utcnow().isoformat() + "Z"


def make_event(
    event_type: str,
    *,
    value: Any = None,
    source: str = "sandbox",
    detail: Optional[Dict[str, Any]] = None,
    t_offset_ms: int = 0,
) -> Dict[str, Any]:
    if event_type not in TELEMETRY_EVENT_TYPES:
        raise ValueError(f"unknown telemetry event: {event_type}")
    return {
        "event_type": event_type,
        "value": value,
        "source": source,
        "detail": detail or {},
        "t_offset_ms": t_offset_ms,
    }


def build_runtime_telemetry_graph(
    events: List[Dict[str, Any]],
    *,
    contract_id: str = "",
    observation_mode: str = "controlled_observational",
    artifact_name: str = "",
) -> Dict[str, Any]:
    """Merge ordered telemetry events into governed graph for replay UI."""
    ordered = sorted(events, key=lambda e: int(e.get("t_offset_ms") or 0))
    summary: Dict[str, Any] = {k: "unknown" for k in TELEMETRY_EVENT_TYPES}

    for ev in ordered:
        et = ev.get("event_type")
        if et in summary and ev.get("value") is not None:
            summary[et] = ev.get("value")

    crash = summary.get("crash_state")
    process = summary.get("process_started")
    if crash in ("observed", "crash", True):
        summary["crash_state"] = "observed"
    elif process in ("yes", True, "started"):
        summary["crash_state"] = summary.get("crash_state") or "none"

    return {
        "graph_version": GRAPH_VERSION,
        "contract_id": contract_id,
        "observation_mode": observation_mode,
        "artifact_name": artifact_name,
        "event_count": len(ordered),
        "timeline": ordered,
        "summary": summary,
        "layer": "raw_telemetry_graph",
        "epistemic_interpretation": "blocked_by_default",
        "invariant_en": "Telemetry density does not imply gameplay understanding.",
        "authority_note_ar": (
            "telemetry timeline استشاري — runtime observation remains advisory until human review."
        ),
        "generated_at": _utc_now(),
    }


def events_from_exe_smoke(smoke: Dict[str, Any], *, base_ms: int = 0) -> List[Dict[str, Any]]:
    """Map smoke_test_windows_exe output to telemetry events."""
    events: List[Dict[str, Any]] = []
    signals = smoke.get("signals") or {}
    artifact = smoke.get("artifact") or "exe"

    if smoke.get("attempted"):
        events.append(make_event(
            "process_started",
            value="yes" if signals.get("runtime_launch_attempted") else "no",
            detail={"artifact": artifact, "smoke_result": smoke.get("smoke_result")},
            t_offset_ms=base_ms,
        ))

    if smoke.get("smoke_result") in ("stable_window", "launch_ok"):
        events.append(make_event(
            "scene_loaded",
            value=signals.get("scene_loaded", "partial"),
            t_offset_ms=base_ms + 500,
        ))

    if signals.get("player_moved") == "detected":
        events.append(make_event(
            "input_detected",
            value="detected",
            t_offset_ms=base_ms + 1200,
        ))

    ran = signals.get("process_ran_seconds")
    if ran is not None:
        events.append(make_event(
            "runtime_duration",
            value=ran,
            detail={"unit": "seconds"},
            t_offset_ms=base_ms + int(float(ran) * 1000) if ran else base_ms + 3000,
        ))

    crash_val = signals.get("crash", "unknown")
    events.append(make_event(
        "crash_state",
        value=crash_val,
        detail={"exit_code": signals.get("exit_code"), "smoke_result": smoke.get("smoke_result")},
        t_offset_ms=base_ms + 4000,
    ))
    return events


def events_from_static_analysis(analysis: Dict[str, Any], *, base_ms: int = 0) -> List[Dict[str, Any]]:
    """Static apk/pck structure → partial telemetry (no process launch)."""
    events: List[Dict[str, Any]] = []
    atype = analysis.get("type") or "artifact"
    signals = analysis.get("signals") or {}

    if analysis.get("valid"):
        events.append(make_event(
            "process_started",
            value="not_attempted",
            detail={"type": atype, "mode": "static_structure_only"},
            t_offset_ms=base_ms,
        ))
        if signals.get("scene_loaded"):
            events.append(make_event(
                "scene_loaded",
                value=signals.get("scene_loaded"),
                detail={"type": atype},
                t_offset_ms=base_ms + 100,
            ))
        if signals.get("level_transition"):
            events.append(make_event(
                "level_transition",
                value=signals.get("level_transition"),
                t_offset_ms=base_ms + 200,
            ))
    return events


def merge_analyses_to_telemetry_graph(
    analyses: List[Dict[str, Any]],
    *,
    contract_id: str = "",
    observation_mode: str = "controlled_observational",
) -> Dict[str, Any]:
    """Build unified telemetry graph from sandbox artifact analyses."""
    all_events: List[Dict[str, Any]] = []
    offset = 0
    primary_name = ""
    for analysis in analyses:
        if not primary_name:
            primary_name = str(analysis.get("artifact") or "")
        if analysis.get("type") == "exe":
            chunk = events_from_exe_smoke(analysis, base_ms=offset)
        else:
            chunk = events_from_static_analysis(analysis, base_ms=offset)
        all_events.extend(chunk)
        offset += 5000

    return build_runtime_telemetry_graph(
        all_events,
        contract_id=contract_id,
        observation_mode=observation_mode,
        artifact_name=primary_name,
    )
