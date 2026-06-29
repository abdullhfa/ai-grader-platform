"""Replay cohort registry tests."""
from __future__ import annotations

import json

from app.replay_cohort_registry import (
    classify_composite_zones,
    classify_replay_cohorts,
    list_cohort_registry,
)


def _runtime_snap() -> dict:
    from app.academic_event_replay import seed_academic_event_log
    from app.explainability_migration import apply_explainability_backfill

    snap, _ = apply_explainability_backfill(
        {
            "grade_level": "U",
            "criteria_results": [{"criteria_level": "8/C.P5", "achieved": False}],
            "artifact_inventory": {
                "executable_artifacts": {"files": [{"name": "g.exe"}]},
                "runtime_observation_report": {"status": "gated"},
            },
        }
    )
    layer = snap.setdefault("explainability_layer", {})
    layer["extraction_coverage"] = {"coverage_ratio": 0.1, "weak_analysis_risk": True}
    seed_academic_event_log(snap)
    return snap


def test_classify_runtime_only_cohort():
    snap = _runtime_snap()
    cohorts = classify_replay_cohorts(snap, procedural_path={"replay_source_synthetic": False})
    assert "runtime_only" in cohorts
    assert "partial_code_extraction" in cohorts


def test_composite_zone():
    zones = classify_composite_zones(["runtime_only", "partial_code_extraction"])
    assert "runtime_only+partial_code_extraction" in zones


def test_list_registry():
    reg = list_cohort_registry()
    assert reg["definition_contract"] == "cohort_v1"
    assert len(reg["cohorts"]) >= 5
    assert "runtime_present" in reg["signals_available"]
