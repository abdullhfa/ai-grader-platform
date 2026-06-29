"""L5 playtest path under GOVERNANCE_FREEZE_v1."""
from __future__ import annotations

from app.runtime_criterion_mapping import (
    apply_runtime_criterion_adjudication,
    evaluate_operational_support,
    observation_allows_adjudication,
)
from app.submission_playtest import get_submission_playtest_state


def test_playtest_available_when_exe_gated():
    snap = {
        "artifact_inventory": {
            "executable_artifacts": {
                "files": [{"name": "game.exe", "path": "/tmp/game.exe", "ext": ".exe"}],
            },
            "runtime_observation_report": {
                "status": "gated",
                "reason": "GOVERNANCE_FREEZE_v1_active",
            },
        },
    }
    state = get_submission_playtest_state(1, snap)
    assert state["playtest_available"] is True
    assert state["l4_gated"] is True
    assert "game.exe" in state["game_executable_path"]


def test_l5_adjudication_under_gate():
    inv = {
        "executable_artifacts": {"files": [{"name": "game.exe"}]},
        "runtime_observation_report": {
            "status": "gated",
            "human_playtest_verified": True,
            "manual_playtest_verified": True,
            "interaction_visually_corroborated": True,
        },
    }
    obs = inv["runtime_observation_report"]
    assert observation_allows_adjudication(obs, inv) is True
    support = evaluate_operational_support(obs, inv)
    assert support["C.P5"]["suggested_achieved"] is True
    result = {
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "score": 0},
            {"criteria_level": "8/C.P6", "achieved": False, "score": 0},
        ],
        "artifact_inventory": inv,
    }
    adj = apply_runtime_criterion_adjudication(result, observation=obs, inventory=inv)
    assert adj["applied"] is True
    cp5 = next(c for c in result["criteria_results"] if "P5" in c["criteria_level"])
    assert cp5["achieved"] is True
    assert cp5["achievement_authority"] == "HUMAN_PLAYTEST_L5"
