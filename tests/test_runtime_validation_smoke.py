"""Runtime smoke pass must not claim launch on structure-only Godot scans."""
from app.runtime.validation_engine import functional_smoke_pass


def test_structure_only_godot_scan_does_not_pass_smoke():
    obs = {
        "status": "completed",
        "observation_mode": "godot_apk_pck_static_scan",
        "game_launch_attempted": False,
        "runtime_verified": False,
    }
    smoke = functional_smoke_pass(obs)
    assert smoke["functional_smoke_pass"] is False
    assert smoke["reason"] == "structure_only_no_game_launch"


def test_observation_completed_alone_does_not_pass_smoke():
    obs = {"status": "completed", "runtime_verified": False, "runtime_observed": False}
    smoke = functional_smoke_pass(obs)
    assert smoke["functional_smoke_pass"] is False
