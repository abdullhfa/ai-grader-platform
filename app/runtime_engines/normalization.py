"""Engine-agnostic runtime output normalization — internal envelope only.

Does NOT modify frozen replay/evidence graph contracts. Produces a stable
internal shape for gameplay, governance, and appeals pipelines.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


NORMALIZATION_SCHEMA = "runtime_observation_v1"


def normalize_runtime_manifest(manifest: Dict[str, Any]) -> Dict[str, Any]:
    """Map any engine manifest to RuntimeObservation + EvidenceBundle envelope."""
    engine = manifest.get("engine") or "unknown"
    signals = manifest.get("signals") or {}
    metrics = manifest.get("metrics") or {}
    events = manifest.get("events") or []
    confidence_tier = manifest.get("confidence_tier") or {}
    submission_validity = manifest.get("submission_validity") or {}

    runtime_method = signals.get("runtime_method") or _infer_runtime_method(engine, signals)
    timeline = _build_gameplay_timeline(events, signals, metrics)

    observation = {
        "schema": NORMALIZATION_SCHEMA,
        "session_id": manifest.get("session_id"),
        "engine_id": engine,
        "submission_key": manifest.get("submission_key"),
        "status": manifest.get("status"),
        "runtime_method": runtime_method,
        "capabilities": manifest.get("capabilities"),
        "metrics": metrics,
        "telemetry": manifest.get("telemetry"),
        "errors": manifest.get("errors") or [],
        "confidence_tier": confidence_tier.get("tier"),
        "confidence_pct": confidence_tier.get("confidence_pct"),
        "examiner_signoff_required": confidence_tier.get("examiner_signoff_required"),
        "submission_validity": submission_validity.get("validity"),
    }

    evidence_bundle = {
        "schema": "evidence_bundle_v1",
        "engine_id": engine,
        "runtime_observation": observation,
        "gameplay_timeline": timeline,
        "artifacts": {
            "screenshots": manifest.get("screenshots") or [],
            "logs": manifest.get("logs") or [],
            "manifest_entries": manifest.get("artifacts") or [],
        },
        "signals": _engine_agnostic_signals(signals),
        "replay_inputs": {
            "session_id": manifest.get("session_id"),
            "engine": engine,
            "runtime_method": runtime_method,
            "status": manifest.get("status"),
            "confidence_tier": confidence_tier.get("tier"),
        },
        "confidence_tier": confidence_tier,
        "submission_validity": submission_validity,
    }

    return {
        "runtime_observation": observation,
        "gameplay_timeline": timeline,
        "evidence_bundle": evidence_bundle,
        "confidence_tier": confidence_tier,
        "submission_validity": submission_validity,
    }


def _infer_runtime_method(engine: str, signals: Dict[str, Any]) -> str:
    if signals.get("runtime_method"):
        return str(signals["runtime_method"])
    mapping = {
        "unity": "unity_play_session",
        "godot": "godot_export_smoke",
        "web": "web_headless",
        "gamemaker": "gamemaker_artifact_analysis",
        "legacy_exe": "legacy_smoke_test",
    }
    return mapping.get(engine, "unknown")


def _build_gameplay_timeline(
    events: List[Dict[str, Any]],
    signals: Dict[str, Any],
    metrics: Dict[str, Any],
) -> Dict[str, Any]:
    timeline_events: List[Dict[str, Any]] = []
    for idx, ev in enumerate(events):
        timeline_events.append(
            {
                "timestamp": float(ev.get("timestamp") or idx),
                "type": ev.get("event") or ev.get("type") or "runtime_event",
                "source": ev.get("source") or "runtime_engine",
                "payload": {k: v for k, v in ev.items() if k not in ("event", "type", "source", "timestamp")},
            }
        )

    if metrics.get("crash_detected"):
        timeline_events.append({"timestamp": 0.0, "type": "crash_detected", "source": "metrics", "payload": {}})
    if metrics.get("freeze_detected"):
        timeline_events.append({"timestamp": 0.0, "type": "freeze_detected", "source": "metrics", "payload": {}})

    gameplay = signals.get("gameplay_analysis") or {}
    if isinstance(gameplay, dict) and gameplay.get("timeline"):
        return gameplay["timeline"]

    duration = max((e["timestamp"] for e in timeline_events), default=0.0)
    return {
        "duration_seconds": duration,
        "event_count": len(timeline_events),
        "events": timeline_events,
    }


def _engine_agnostic_signals(signals: Dict[str, Any]) -> Dict[str, Any]:
    keys = (
        "runtime_method",
        "artifact_analysis",
        "yyp_metadata",
        "gamemaker_layout",
        "gamemaker_observation",
        "unity_layout",
        "scene_validation",
        "export_attempt",
        "godot_layout",
        "godot_project_analysis",
        "godot_observation",
        "legacy_observation",
        "entry_html",
    )
    return {k: signals[k] for k in keys if k in signals}
