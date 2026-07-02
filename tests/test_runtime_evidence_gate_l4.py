"""Runtime evidence gate tests with automated L4."""
from __future__ import annotations

from app.runtime_evidence_gate import apply_runtime_evidence_gate


def test_runtime_gate_opens_cp5_on_l4_partial():
    criteria = [
        {"criteria_level": "8/C.P5", "achieved": True, "score": 75, "feedback": "ok"},
        {"criteria_level": "8/C.P6", "achieved": True, "score": 70, "feedback": "ok"},
    ]
    gr = {
        "grade_level": "P",
        "criteria_results": criteria,
        "artifact_inventory": {
            "runtime_validation": {"functional_smoke": {"functional_smoke_pass": True}},
            "intake_relative_paths": ["P_03.exe"],
            "gameplay_verification": {
                "l4_level": "L4_partial",
                "player_movement_verified": True,
                "mechanics_verified_count": 1,
                "gameplay_window_screenshots": 2,
            },
            "runtime_observation_report": {
                "status": "completed",
                "gameplay_verification": {
                    "l4_level": "L4_partial",
                    "player_movement_verified": True,
                    "mechanics_verified_count": 1,
                    "gameplay_window_screenshots": 2,
                },
            },
            "executable_artifacts": {"files": ["P_03.exe"]},
            "runtime_artifacts": {"godot_export_detected": True},
        },
        "submission_paths": ["uploads/student/P_03.exe"],
    }
    report = apply_runtime_evidence_gate(gr)
    cp5 = gr["criteria_results"][0]
    cp6 = gr["criteria_results"][1]
    assert not cp5.get("runtime_gate_block")
    assert report.get("automated_l4_gate", {}).get("criterion_pass", {}).get("P6") is False
    assert "runtime_gate_l4_open" in ",".join(report.get("changes") or [])
