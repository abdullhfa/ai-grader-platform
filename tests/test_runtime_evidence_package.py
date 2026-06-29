"""Tests for PRO v1 runtime evidence package."""
from app.evidence_coverage_score import attach_evidence_coverage_package
from app.requirement_checklist import build_requirement_checklist
from app.runtime_evidence_package import attach_runtime_evidence_package, build_runtime_evidence_package


def _sample_observation():
    return {
        "status": "completed",
        "runtime_verified": True,
        "runtime_observed": True,
        "runtime_screenshots": [
            {"label": "launch", "path": "/tmp/startup.png", "status": "captured", "elapsed_seconds": 2},
            {"label": "mid_runtime", "path": "/tmp/5s.png", "status": "captured", "elapsed_seconds": 5},
        ],
        "artifact_analyses": [
            {"type": "exe", "smoke_result": "stable_window", "signals": {"crash": "none"}},
        ],
        "runtime_signal_graph": {
            "signals": {
                "interaction_input_sent": "yes",
                "visual_response_to_input": "partial",
                "scene_loaded": "partial",
            }
        },
    }


def test_build_package_pass_with_events():
    inv = {
        "runtime_observation_report": _sample_observation(),
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        "intake_relative_paths": ["project.godot"],
    }
    checklist = build_requirement_checklist(student_text="player jump score")
    pkg = build_runtime_evidence_package(
        artifact_inventory=inv,
        requirement_checklist=checklist,
        submission_paths=["game.exe"],
    )
    assert pkg["runtime_status"] == "PASS"
    assert pkg["runtime_evidence_strength"] in ("STRONG", "MODERATE")
    events = {e["event"] for e in pkg["events"]}
    assert "launch_success" in events
    assert "movement_observed" in events
    assert pkg["does_not_imply_grade"] is True


def test_screenshots_from_gamemaker_gameplay_replay():
    inv = {
        "runtime_observation_report": {
            "status": "completed",
            "runtime_verified": True,
            "runtime_observed": True,
            "gamemaker_gameplay_replay": {
                "method": "exe_smoke",
                "screenshots": [
                    "uploads/replay_snapshots/student/uuid/runtime/startup.png",
                    "uploads/replay_snapshots/student/uuid/runtime/5s.png",
                    "uploads/replay_snapshots/student/uuid/runtime/15s.png",
                ],
            },
            "artifact_analyses": [
                {"type": "exe", "smoke_result": "stable_window", "signals": {"crash": "none"}},
            ],
        },
        "executable_artifacts": {"files": [{"name": "CheeseChase.exe"}]},
    }
    pkg = build_runtime_evidence_package(artifact_inventory=inv)
    assert len(pkg["screenshots"]) == 3
    slots = {s["slot"] for s in pkg["screenshots"]}
    assert "startup" in slots
    assert "5s" in slots
    assert "15s" in slots
    assert all(s.get("url") for s in pkg["screenshots"])


def test_package_boosts_coverage_not_grade_directly():
    inv = {
        "runtime_observation_report": _sample_observation(),
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        "source_code": {"files": [{"name": "main.gd"}]},
    }
    grading = {
        "criteria_results": [{"criteria_level": "8/C.P5"}, {"criteria_level": "8/C.P6"}],
        "grade_level": "U",
    }
    attach_runtime_evidence_package(grading, artifact_inventory=inv)
    attach_evidence_coverage_package(grading, artifact_inventory=inv, student_text="test plan")
    p5_row = None
    for row in grading.get("evidence_coverage_by_criterion") or []:
        if not isinstance(row, dict):
            continue
        level = row.get("criteria_level") or ""
        if isinstance(level, str) and level.endswith("P5"):
            p5_row = row
            break
    assert p5_row is not None
    assert int(p5_row.get("coverage_pct") or 0) >= 50
