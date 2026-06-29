"""Tests for build_evidence_map (Phase 2)."""
from __future__ import annotations

from app.evidence_map import build_evidence_map, build_evidence_map_summary


def _scratch_snapshot() -> dict:
    return {
        "grading_mode": "deep",
        "submission_paths": ["game/project.sb3"],
        "artifact_inventory": {
            "runtime_artifacts": {"scratch_detected": True},
            "has_executable_artifacts": True,
            "executable_artifacts": {"files": [{"ext": ".sb3", "artifact_kind": "scratch_project"}]},
        },
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "awardable": False, "runtime_gate_block": True},
            {"criteria_level": "8/C.P6", "achieved": False, "awardable": False, "runtime_gate_block": True},
        ],
        "runtime_evidence_gate": {
            "applied": True,
            "satisfied": False,
            "summary_ar": "لا يوجد فيديو تشغيل",
        },
    }


def test_evidence_map_gate_rows():
    rows = build_evidence_map(_scratch_snapshot())
    assert len(rows) == 2
    p5 = next(r for r in rows if r["criterion_code"] == "P5")
    assert p5["gate_relevant"] is True
    assert p5["gate_applied"] is True
    assert p5["gate_satisfied"] is False
    assert p5["achieved_final"] is False


def test_evidence_map_summary_flags_gate():
    rows = build_evidence_map(_scratch_snapshot())
    summary = build_evidence_map_summary(rows)
    assert summary["has_gate_issue"] is True
    assert summary["gate_downgrade_count"] >= 1


def test_evidence_map_empty_snapshot():
    assert build_evidence_map(None) == []
    assert build_evidence_map({}) == []
