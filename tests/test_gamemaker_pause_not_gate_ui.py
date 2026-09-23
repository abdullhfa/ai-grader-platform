"""UI/radar: GameMaker install-pause must not look like C.P5/C.P6 Gate."""
from __future__ import annotations

from app.evidence_map import build_evidence_summary_from_snapshot


def test_paused_snapshot_not_counted_as_gate_issue():
    snap = {
        "grading_paused": {
            "paused": True,
            "reason": "gamemaker_not_installed",
            "short_ar": "⏸ معلّق — ثبّت GameMaker ثم أعد التصحيح",
        },
        "gamemaker_install_pause_banner": {"active": True},
        "criteria_results": [
            {
                "criteria_level": "C.P5",
                "achieved": False,
                "runtime_gate_block": True,
            },
            {
                "criteria_level": "C.P6",
                "achieved": False,
                "runtime_gate_block": True,
            },
        ],
        "submission_paths": ["student/project.yyp", "student/Create_0.gml"],
        "artifact_inventory": {},
    }
    summary = build_evidence_summary_from_snapshot(snap)
    assert summary["has_gate_issue"] is False
    assert summary["gate_downgrade_count"] == 0
    assert summary["grading_paused"] is True
