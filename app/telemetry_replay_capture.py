"""
Telemetry + replay capture wiring — two-layer architecture, no legitimacy inference.

Invariants:
  Telemetry density does not imply gameplay understanding.
  Replay is evidence of reproducibility, not evidence of validity.
  execution visibility ≠ execution comprehension
"""
from __future__ import annotations

import re
import uuid
from typing import Any, Dict, FrozenSet, List, Optional, Tuple

from app.execution_phenomenology import build_phenomenology_record, validate_phenomenology_text
from app.phenomenology_manifest import MANIFEST_ID, descriptors, domain_invariant, forbidden_escalations
from app.runtime_telemetry_graph import build_runtime_telemetry_graph

SPEC_ID = "TELEMETRY_REPLAY_CAPTURE_WIRING_v1"
REPLAY_SCHEMA_ID = MANIFEST_ID

PRIMARY_INVARIANT_EN = "Telemetry density does not imply gameplay understanding."
REPLAY_INVARIANT_EN = domain_invariant("replay")
VISIBILITY_COMPREHENSION_EN = "execution visibility ≠ execution comprehension"

RAW_TELEMETRY_TYPES: FrozenSet[str] = frozenset({
    "fps_sample",
    "frame_event",
    "process_lifecycle",
    "input_timestamp",
    "crash_signal",
    "render_continuity",
})

REPLAY_PHENOMENOLOGY_DESCRIPTORS = descriptors("replay")
REPLAY_FORBIDDEN_ESCALATIONS = forbidden_escalations("replay")

REPLAY_ESCALATION_PAIRS: List[Tuple[str, str]] = [
    ("replay_captured", "gameplay verified"),
    ("replay_deterministic", "submission authentic"),
    ("replay_reproducible", "rubric satisfied"),
    ("replay_continuous", "mechanics validated"),
]

REPLAY_FORBIDDEN_PATTERNS: List[Tuple[str, str]] = [
    (r"\bgameplay\s+verified\b", "replay captured — reproducibility only"),
    (r"\bsubmission\s+authentic\b", "replay deterministic — not authenticity"),
    (r"\brubric\s+satisfied\b", "replay reproducible — not rubric claim"),
    (r"\bmechanics\s+validated\b", "replay continuous — observation only"),
    (r"\bgameplay\s+understood\b", "telemetry density — not comprehension"),
    (r"\bsystem\s+understands\b", "raw telemetry — capture only"),
]


def make_raw_trace(
    signal_type: str,
    *,
    value: Any = None,
    t_offset_ms: int = 0,
    detail: Optional[Dict[str, Any]] = None,
    source: str = "sandbox",
) -> Dict[str, Any]:
    """Raw telemetry trace — phenomenological capture, no interpretation."""
    if signal_type not in RAW_TELEMETRY_TYPES:
        raise ValueError(f"unknown raw telemetry type: {signal_type}")
    return {
        "layer": "raw_telemetry",
        "signal_type": signal_type,
        "value": value,
        "t_offset_ms": t_offset_ms,
        "source": source,
        "detail": detail or {},
        "assigns_legitimacy": False,
        "assigns_comprehension": False,
        "invariant_en": PRIMARY_INVARIANT_EN,
    }


def build_epistemic_interpretation_stub(*, blocked: bool = True) -> Dict[str, Any]:
    """Epistemic interpretation layer — blocked by default."""
    return {
        "layer": "epistemic_interpretation",
        "blocked": blocked,
        "default_state": "blocked",
        "unlock_requires": "human_governed_explicit_gate",
        "claims": [],
        "note_en": "Signal density does not auto-unlock comprehension.",
        "invariant_en": VISIBILITY_COMPREHENSION_EN,
    }


def build_replay_phenomenology_record(
    descriptors: List[str],
    *,
    t_offset_ms: int = 0,
    detail: Optional[Dict[str, Any]] = None,
    checksum: str = "",
) -> Dict[str, Any]:
    unknown = [d for d in descriptors if d not in REPLAY_PHENOMENOLOGY_DESCRIPTORS]
    if unknown:
        raise ValueError(f"unknown replay phenomenology descriptor(s): {', '.join(unknown)}")
    return {
        "manifest_id": REPLAY_SCHEMA_ID,
        "domain": "replay",
        "spec_id": SPEC_ID,
        "layer": "replay_phenomenology",
        "descriptors": list(descriptors),
        "t_offset_ms": t_offset_ms,
        "checksum": checksum or "",
        "detail": detail or {},
        "invariant_en": REPLAY_INVARIANT_EN,
    }


def validate_replay_phenomenology_text(text: str) -> Dict[str, Any]:
    violations: List[Dict[str, str]] = []
    lower = (text or "").lower()
    for forbidden in REPLAY_FORBIDDEN_ESCALATIONS:
        if forbidden.replace("_", " ") in lower or forbidden in lower:
            violations.append({"type": "forbidden_escalation", "phrase": forbidden})
    for pattern, suggested in REPLAY_FORBIDDEN_PATTERNS:
        if re.search(pattern, text or "", re.IGNORECASE):
            violations.append({"type": "pattern", "pattern": pattern, "suggested": suggested})
    phen = validate_phenomenology_text(text)
    violations.extend(phen.get("violations") or [])
    return {
        "manifest_id": REPLAY_SCHEMA_ID,
        "domain": "replay",
        "allowed": len(violations) == 0,
        "violations": violations,
        "invariant_en": REPLAY_INVARIANT_EN,
    }


def raw_traces_from_graph_events(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Map governed graph events to raw phenomenological traces."""
    traces: List[Dict[str, Any]] = []
    type_map = {
        "process_started": "process_lifecycle",
        "scene_loaded": "frame_event",
        "input_detected": "input_timestamp",
        "score_changed": "frame_event",
        "collision_detected": "frame_event",
        "level_transition": "render_continuity",
        "runtime_duration": "process_lifecycle",
        "crash_state": "crash_signal",
    }
    for ev in events:
        et = ev.get("event_type") or ""
        raw_type = type_map.get(et)
        if not raw_type:
            continue
        traces.append(make_raw_trace(
            raw_type,
            value=ev.get("value"),
            t_offset_ms=int(ev.get("t_offset_ms") or 0),
            detail={"mapped_from": et, **(ev.get("detail") or {})},
            source=str(ev.get("source") or "sandbox"),
        ))
    return traces


def build_provenance_chain_segment(
    *,
    artifact_name: str,
    capture_id: str = "",
    prior_segment_id: str = "",
) -> Dict[str, Any]:
    seg_id = capture_id or f"cap_{uuid.uuid4().hex[:12]}"
    return {
        "segment_id": seg_id,
        "artifact_name": artifact_name,
        "prior_segment_id": prior_segment_id or None,
        "continuity_observed": prior_segment_id is not None,
        "assigns_legitimacy": False,
        "note_en": "Provenance chain segment — observation continuity, not validation.",
    }


def wire_telemetry_replay_capture(
    events: List[Dict[str, Any]],
    *,
    artifact_name: str = "",
    observation_mode: str = "controlled_observational",
    contract_id: str = "",
    replay_descriptors: Optional[List[str]] = None,
    prior_provenance_segment_id: str = "",
) -> Dict[str, Any]:
    """
    Wire raw telemetry + graph + replay phenomenology + blocked interpretation.
    Does NOT append to ledger — caller decides.
    """
    graph = build_runtime_telemetry_graph(
        events,
        contract_id=contract_id,
        observation_mode=observation_mode,
        artifact_name=artifact_name,
    )
    raw_traces = raw_traces_from_graph_events(graph.get("timeline") or [])
    replay_phen = None
    if replay_descriptors:
        replay_phen = build_replay_phenomenology_record(replay_descriptors)
    exec_phen_descriptors: List[str] = []
    if raw_traces:
        exec_phen_descriptors.append("telemetry_stream_active")
    if replay_phen:
        exec_phen_descriptors.append("replay_captured")
    exec_phen = build_phenomenology_record(exec_phen_descriptors) if exec_phen_descriptors else None
    provenance = build_provenance_chain_segment(
        artifact_name=artifact_name,
        prior_segment_id=prior_provenance_segment_id,
    )
    bundle = {
        "spec_id": SPEC_ID,
        "wiring_id": f"trcw_{uuid.uuid4().hex[:12]}",
        "assigns_authority": False,
        "assigns_legitimacy": False,
        "invariants": {
            "telemetry_density": PRIMARY_INVARIANT_EN,
            "replay": REPLAY_INVARIANT_EN,
            "visibility_comprehension": VISIBILITY_COMPREHENSION_EN,
        },
        "raw_telemetry": {
            "layer": "raw_telemetry",
            "trace_count": len(raw_traces),
            "traces": raw_traces,
            "mode": "phenomenological_traces_only",
        },
        "telemetry_graph": graph,
        "replay_phenomenology": replay_phen,
        "execution_phenomenology": exec_phen,
        "provenance_chain_segment": provenance,
        "epistemic_interpretation": build_epistemic_interpretation_stub(blocked=True),
        "forbidden": [
            "gameplay_understood",
            "high_resolution_legitimacy_summary",
        ],
    }
    summary_probe = (
        f"Telemetry traces: {len(raw_traces)}. "
        f"Replay descriptors: {replay_descriptors or []}."
    )
    replay_check = validate_replay_phenomenology_text(summary_probe)
    bundle["replay_phenomenology_check"] = replay_check
    return bundle


def wire_from_sandbox_analyses(
    analyses: List[Dict[str, Any]],
    *,
    contract_id: str = "",
    observation_mode: str = "controlled_observational",
    replay_descriptors: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Convenience: build events from sandbox analyses then wire capture bundle."""
    from app.runtime_telemetry_graph import events_from_exe_smoke, events_from_static_analysis

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
    default_replay = replay_descriptors
    if default_replay is None and all_events:
        default_replay = ["replay_captured"]
    return wire_telemetry_replay_capture(
        all_events,
        artifact_name=primary_name,
        observation_mode=observation_mode,
        contract_id=contract_id,
        replay_descriptors=default_replay,
    )
