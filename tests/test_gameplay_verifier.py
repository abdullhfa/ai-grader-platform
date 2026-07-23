"""Tests for automated L4 gameplay verification."""
from __future__ import annotations

from app.gameplay_verifier import (
    MENU_NAV_WINDOW_LOST,
    MenuNavigator,
    assess_automated_l4_gate,
    build_gameplay_checks_from_verification,
    format_agent_play_summary_ar,
    resolve_gameplay_evidence_level,
)


def test_menu_navigator_reports_window_lost_not_scene_change_failure(tmp_path):
    navigator = MenuNavigator(max_attempts=2)

    def capture(*_args, **_kwargs):
        return {"capture_scope": "capture_lost", "errors": ["RUNTIME_CAPTURE_LOST"]}

    outcome = navigator.detect_and_enter_gameplay(
        artifact_path=tmp_path / "CheeseChase.exe",
        process_pid=123,
        capture_screenshot=capture,
        elapsed_seconds=0,
    )
    assert outcome["status"] == MENU_NAV_WINDOW_LOST
    assert outcome["reason_code"] == "RUNTIME_CAPTURE_LOST"


def test_assess_automated_l4_gate_cp5_partial():
    gv = {
        "l4_level": "L4_partial",
        "player_movement_verified": True,
        "mechanics_verified_count": 1,
        "gameplay_window_screenshots": 2,
    }
    gate = assess_automated_l4_gate(
        gv,
        test_document_present=False,
        functional_smoke_pass=True,
    )
    assert gate["criterion_pass"]["P5"] is True
    assert gate["criterion_pass"]["P6"] is False


def test_assess_automated_l4_gate_cp6_with_test_doc():
    gv = {
        "l4_level": "L4_partial",
        "player_movement_verified": True,
        "mechanics_verified_count": 2,
        "gameplay_window_screenshots": 2,
    }
    gate = assess_automated_l4_gate(
        gv,
        test_document_present=True,
        functional_smoke_pass=True,
    )
    assert gate["criterion_pass"]["P5"] is True
    assert gate["criterion_pass"]["P6"] is True


def test_build_gameplay_checks_from_verification():
    checks = build_gameplay_checks_from_verification(
        {
            "gameplay_entered": True,
            "movement_verification": {
                "player_movement_verified": True,
                "jump_detected": True,
                "score_change_detected": False,
            },
        }
    )
    assert checks["scene_transition"]["observed"] is True
    assert checks["player_movement"]["observed"] is True
    assert checks["jump_mechanic"]["observed"] is True


def test_format_agent_play_summary_l4_full():
    label = format_agent_play_summary_ar("L4", {"l4_level": "L4_full"})
    assert "L4 كامل" in label


def test_resolve_level_from_automated_verification():
    obs = {
        "status": "completed",
        "runtime_observed": True,
        "gameplay_verification": {
            "l4_level": "L4_partial",
            "player_movement_verified": True,
        },
    }
    assert resolve_gameplay_evidence_level(obs) == "L4"
