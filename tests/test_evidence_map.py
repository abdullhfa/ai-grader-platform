"""Tests for build_evidence_map (Phase 2)."""
from __future__ import annotations

from app.evidence_map import (
    build_evidence_map,
    build_evidence_map_summary,
    build_evidence_summary_from_snapshot,
)


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
    assert summary["has_evidence_issue"] is True
    assert summary["gate_downgrade_count"] >= 1


def test_evidence_summary_from_snapshot_lightweight():
    snap = _scratch_snapshot()
    snap["evidence_coverage_by_criterion"] = [
        {"criteria_level": "8/C.P5", "coverage_pct": 60},
        {"criteria_level": "8/C.P6", "coverage_pct": 40},
    ]
    summary = build_evidence_summary_from_snapshot(snap)
    assert summary["has_gate_issue"] is True
    assert summary["gate_downgrade_count"] == 2
    assert summary["high_coverage_not_achieved_count"] == 1
    assert summary["has_evidence_issue"] is True


def test_evidence_summary_from_snapshot_empty():
    summary = build_evidence_summary_from_snapshot(None)
    assert summary["has_gate_issue"] is False
    assert summary["high_coverage_not_achieved_count"] == 0


def test_evidence_map_uses_arabic_coverage_keys():
    snap = {
        "criteria_results": [{"criteria_level": "8/C.P5", "achieved": False}],
        "artifact_inventory": {"has_executable_artifacts": True, "runtime_artifacts": {"scratch_detected": True}},
        "submission_paths": ["game.sb3"],
        "evidence_coverage_by_criterion": [
            {
                "criteria_level": "8/C.P5",
                "coverage_pct": 50,
                "evidence_found_ar": ["كود مصدري / مشروع"],
                "evidence_missing_ar": ["تشغيل مُتحقق (L4+)"],
            }
        ],
    }
    rows = build_evidence_map(snap)
    p5 = next(r for r in rows if r["criterion_code"] == "P5")
    assert "كود مصدري" in p5["available_evidence"][0]
    assert "تشغيل" in p5["missing_evidence"][0]


def test_evidence_map_empty_snapshot():
    assert build_evidence_map(None) == []
    assert build_evidence_map({}) == []
