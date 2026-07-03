"""Tests for scripts/godot_trial_runner.py."""
from __future__ import annotations

from scripts.godot_trial_runner import build_trial_report, compare_trial_reports


def test_build_trial_report_from_observation():
    obs = {
        "runtime_observed": True,
        "runtime_screenshots": [{"status": "captured"}] * 10,
        "gameplay_verification": {
            "gameplay_entered": True,
            "l4_level": "L4_partial",
            "godot_retry_attempts": [{"step": "play_pass_1"}],
        },
        "interaction_trace": {"errors": []},
    }
    report = build_trial_report(
        obs,
        exe_path="uploads/students/hamtini_u8/final.exe",
        duration_ms=35000,
    )
    assert report["gates_passed"] is True
    assert report["gameplay_entered"] is True
    assert report["profile_guess"] == "direct_gameplay"
    assert report["screenshot_count"] == 10


def test_build_trial_report_simple_menu_profile():
    obs = {
        "runtime_observed": True,
        "runtime_screenshots": [{"status": "captured"}] * 8,
        "gameplay_verification": {
            "gameplay_entered": True,
            "godot_retry_attempts": [{"step": "nav_pass_1"}, {"step": "play_pass_1"}],
        },
        "interaction_trace": {"errors": []},
    }
    report = build_trial_report(
        obs,
        exe_path="uploads/students/hamtini_u8/farst game.exe",
        duration_ms=40000,
    )
    assert report["profile_guess"] == "simple_menu"


def test_compare_prefers_final_on_tie():
    farst = {
        "exe_path": "uploads/students/hamtini_u8/farst game.exe",
        "gates_passed": True,
        "gameplay_entered": True,
        "failure_reason_code": None,
        "profile_guess": "direct_gameplay",
        "duration_ms": 40000,
        "interaction_errors": [],
    }
    final = {
        **farst,
        "exe_path": "uploads/students/hamtini_u8/final.exe",
        "duration_ms": 38000,
    }
    winner = compare_trial_reports([farst, final])
    assert "final.exe" in winner["exe_path"]


def test_compare_prefers_gates_passed():
    bad = {
        "exe_path": "uploads/students/hamtini_u8/final.exe",
        "gates_passed": False,
        "gameplay_entered": None,
        "failure_reason_code": None,
        "profile_guess": "unknown",
        "duration_ms": 30000,
        "interaction_errors": [],
    }
    good = {
        **bad,
        "exe_path": "uploads/students/hamtini_u8/farst game.exe",
        "gates_passed": True,
        "gameplay_entered": False,
        "failure_reason_code": "PROCESS_CRASHED",
    }
    winner = compare_trial_reports([bad, good])
    assert "farst game.exe" in winner["exe_path"]
