"""Counterfactual governance drift detection tests."""
from __future__ import annotations

import json

from app.academic_event_replay import seed_academic_event_log
from app.counterfactual_replay import (
    append_drift_artifact_to_snapshot,
    detect_governance_drift,
)
from app.explainability_migration import apply_explainability_backfill


def _events_snap() -> tuple[list, dict]:
    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "U",
            "total_score": 0,
            "max_score": 100,
            "percentage": 0.0,
            "criteria_results": [
                {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
                {"criteria_level": "8/C.P6", "achieved": False, "score": 0},
            ],
            "artifact_inventory": {
                "executable_artifacts": {"files": [{"name": "game.exe"}]},
                "runtime_observation_report": {
                    "status": "gated",
                    "reason": "GOVERNANCE_FREEZE_v1_active",
                },
            },
        }
    )
    seed_academic_event_log(snap)
    return snap["academic_event_log"]["events"], snap


def test_counterfactual_drift_v1_vs_v2():
    events, snap = _events_snap()
    ctx = {"evidence_lineage": snap.get("evidence_lineage") or snap.get("explainability_layer", {}).get("evidence_lineage")}
    report = detect_governance_drift(
        events,
        baseline_contract="GOVERNANCE_v1",
        comparison_contract="GOVERNANCE_v2",
        sandbox_context=ctx,
    )
    drift = report["drift"]
    assert drift["counterfactual"] is True
    assert drift["baseline_epoch"] == "GOVERNANCE_v1"
    assert drift["comparison_epoch"] == "GOVERNANCE_v2"
    assert drift.get("artifact_hash")
    assert "disclaimer_ar" in drift


def test_drift_artifact_append_only():
    events, snap = _events_snap()
    report = detect_governance_drift(events)
    before = json.dumps(snap, sort_keys=True)
    updated = append_drift_artifact_to_snapshot(dict(snap), report)
    assert len(updated.get("counterfactual_drift_artifacts") or []) == 1
    assert updated["grade_level"] == snap["grade_level"]
    assert updated["criteria_results"] == snap["criteria_results"]


def test_sandbox_does_not_mutate_original_snapshot():
    events, snap = _events_snap()
    orig_grade = snap["grade_level"]
    detect_governance_drift(events)
    assert snap["grade_level"] == orig_grade
    assert "counterfactual_drift_artifacts" not in snap
