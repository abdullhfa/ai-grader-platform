from app.gameplay_semantic_verification import assess_gameplay_semantics
from app.institutional_grade_resolution import resolve_institutional_classification


def _inventory_with_verified_loop():
    requirements = [
        "player_movement",
        "score_system",
        "collect_items",
        "lives_system",
        "enemy_interaction",
        "win_lose_condition",
        "restart",
    ]
    gv = {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "requirement_results": [
            {"req_id": req_id, "verified": True} for req_id in requirements
        ],
    }
    return {
        "runtime_observation_report": {
            "runtime_observed": True,
            "status": "completed",
            "gameplay_verification": gv,
        },
        "gameplay_verification": gv,
        "executable_artifacts": {"files": ["game.exe"], "runtime_observed": True},
    }


def test_semantics_consumes_authoritative_requirement_results():
    inventory = _inventory_with_verified_loop()

    result = assess_gameplay_semantics(
        inventory["runtime_observation_report"], inventory=inventory
    )

    assert result["gameplay_loop_complete"] is True
    assert result["score_progression_detected"] is True
    assert result["restart_flow_detected"] is True
    assert result["lives_or_health_detected"] is True
    assert result["verification_level"] == "L5_verified"


def test_autonomous_mode_does_not_require_examiner_signoff(monkeypatch):
    monkeypatch.setenv("AUTONOMOUS_GRADING", "true")
    grading = {
        "grade_level": "M",
        "percentage": 75,
        "criteria_results": [
            {"criteria_level": "C.P5", "achieved": True},
            {"criteria_level": "C.M3", "achieved": True},
        ],
    }

    resolution = resolve_institutional_classification(
        grading, artifact_inventory=_inventory_with_verified_loop()
    )

    assert resolution["examiner_signoff_required"] is False
