"""Tests for PRO v1 runtime evidence package."""
from app.evidence_coverage_score import attach_evidence_coverage_package
from app.academic_explainability import build_missing_evidence_diagnostics
from app.explainability_migration import extract_explainability_for_ui
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


def _gamemaker_l4_inventory():
    verification = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "automated_l4_level": "L4_full",
        "evidence_package": {
            "results": [
                {"req_id": "menu_navigation", "verified": True, "confidence": 0.91},
                {"req_id": "player_movement", "verified": True, "confidence": 1.0},
                {"req_id": "score_system", "verified": True, "confidence": 0.96},
                {"req_id": "lives_system", "verified": True, "confidence": 0.87},
                {"req_id": "timer_system", "verified": False, "confidence": 0.06},
            ]
        },
    }
    return {
        "gameplay_verification": verification,
        "runtime_observation_report": {
            **_sample_observation(),
            "engine": "gamemaker",
            "gameplay_verification": verification,
        },
        "executable_artifacts": {
            "status": "analyzed",
            "runtime_verified": True,
            "files": [{"name": "CheeseChase.exe"}],
        },
    }


def test_gamemaker_l4_requirement_results_drive_confidence_rows():
    inv = _gamemaker_l4_inventory()
    checklist = {
        "requirements": [
            {"id": "menu_ui", "label_ar": "واجهة / قائمة"},
            {"id": "player_movement", "label_ar": "حركة اللاعب"},
            {"id": "score_system", "label_ar": "نظام النقاط"},
            {"id": "lives_system", "label_ar": "نظام الحياة"},
            {"id": "timer_system", "label_ar": "نظام الوقت"},
        ]
    }
    pkg = build_runtime_evidence_package(
        artifact_inventory=inv,
        requirement_checklist=checklist,
        submission_paths=["CheeseChase.exe"],
    )
    rows = {row["requirement"]: row for row in pkg["requirement_confidence"]}
    assert pkg["runtime_gameplay_verified"] is True
    assert pkg["gameplay_entered"] is True
    assert pkg["l4_level"] == "L4_full"
    assert pkg["gameplay_evidence_level"] == "L4"
    assert rows["menu_ui"]["confidence_pct"] == 91
    assert rows["player_movement"]["confidence_pct"] == 100
    assert rows["score_system"]["verified"] is True
    assert rows["lives_system"]["confidence_pct"] == 87
    assert rows["timer_system"]["verified"] is False
    assert rows["timer_system"]["confidence_pct"] == 6
    assert all(row["confidence_source"] == "runtime_l4" for row in rows.values())


def test_gamemaker_l4_gameplay_is_not_relabelled_as_needing_l5():
    diag = build_missing_evidence_diagnostics(_gamemaker_l4_inventory(), grading_mode="full")
    runtime_row = next(
        row for row in diag["rows"]
        if row["requirement_ar"] == "التحقق من التشغيل (runtime)"
    )
    assert runtime_row["present"] is True
    assert "L4_full" in runtime_row["status_ar"]
    assert "بدون L5" not in runtime_row["status_ar"]
    assert runtime_row["blocks_achievement_ar"] == ""


def test_ui_rebuilds_stale_runtime_package_for_existing_results():
    inv = _gamemaker_l4_inventory()
    checklist = {
        "requirements": [
            {"id": "player_movement", "label_ar": "حركة اللاعب"},
            {"id": "score_system", "label_ar": "نظام النقاط"},
        ]
    }
    snapshot = {
        "artifact_inventory": inv,
        "requirement_checklist": checklist,
        "runtime_evidence_package": {
            "version": "runtime_evidence_package_v1",
            "requirement_confidence": [
                {"requirement": "player_movement", "confidence_pct": 0}
            ],
        },
    }
    ui = extract_explainability_for_ui(snapshot)
    assert ui is not None
    package = ui["runtime_evidence_package"]
    assert package["version"] == "runtime_evidence_package_v2"
    rows = {row["requirement"]: row for row in package["requirement_confidence"]}
    assert rows["player_movement"]["confidence_pct"] == 100
    assert rows["score_system"]["verified"] is True
