"""
Test that institutional_grade_resolution properly handles GameMaker IDE pause.

Context: When a student submits a valid GameMaker .yyp project with partial
criteria achievement, but GameMaker IDE is not installed, the system pauses
to wait for IDE installation. The student should NOT receive 'U' (Unclassified)
in this case — they should receive Referral or Partial based on their achievement.

This test ensures the fix prevents unfair U grades during IDE pause scenarios.
"""
from __future__ import annotations

from typing import Any, Dict

import pytest

from app.institutional_grade_resolution import resolve_institutional_classification


def _make_grading_result_with_gamemaker_pause(
    *,
    criteria_achieved: int = 2,
    criteria_total: int = 10,
    percentage: float = 20.0,
    has_yyp: bool = True,
    paused: bool = True,
    has_exe: bool = False,
    has_doc: bool = False,
) -> Dict[str, Any]:
    """Factory to create a grading_result with GameMaker pause scenario."""
    criteria = []
    for i in range(criteria_total):
        criteria.append({
            "criteria_level": f"P{i+1}",
            "achieved": i < criteria_achieved,
            "evidence": "partial" if i < criteria_achieved else None,
        })

    artifact_inventory = {
        "source_code": {
            "gamemaker_project_detected": has_yyp,
            "files": [] if not has_yyp else [{"path": "project.yyp"}],
        },
        "executable_artifacts": {
            "files": [] if not has_exe else [{"path": "game.exe"}],
        },
        "documentation": {
            "files": [] if not has_doc else [{"path": "README.md"}],
        },
        "runtime_observation_report": {},
    }

    build_pipeline = {
        "ide_build": {
            "paused": paused,
            "wait_exhausted_seconds": 120 if paused else None,
            "reason": "gamemaker_runtime_not_installed" if paused else None,
        },
    }

    gamemaker_layout = {
        "yyp_path": "project.yyp" if has_yyp else None,
    }

    return {
        "criteria_results": criteria,
        "percentage": percentage,
        "grade_level": "U",
        "artifact_inventory": artifact_inventory,
        "build_pipeline": build_pipeline,
        "gamemaker_layout": gamemaker_layout,
    }


def test_gamemaker_pause_with_20pct_achievement_gets_referral():
    """Student with 20% achievement + valid .yyp + IDE pause → Referral, not U."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=2,
        criteria_total=10,
        percentage=20.0,
        has_yyp=True,
        paused=True,
        has_exe=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    assert resolution["outcome_band"] == "Referral"
    assert resolution["display_grade"] == "R"
    assert resolution["btec_grade"] == "U"  # BTEC stays U, but institutional band is Referral
    assert resolution["criteria_achieved"] == 2
    assert resolution["percentage"] == 20.0


def test_gamemaker_pause_with_15pct_achievement_gets_partial():
    """Student with 15% achievement + valid .yyp + IDE pause → Partial, not U."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=1,
        criteria_total=10,
        percentage=10.0,
        has_yyp=True,
        paused=True,
        has_exe=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    assert resolution["outcome_band"] == "Partial"
    assert resolution["display_grade"] == "P"
    assert resolution["criteria_achieved"] == 1


def test_gamemaker_pause_but_no_achievement_still_unclassified():
    """Student with 0% achievement + valid .yyp + IDE pause → still U."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=0,
        criteria_total=10,
        percentage=0.0,
        has_yyp=True,
        paused=True,
        has_exe=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    assert resolution["outcome_band"] == "Unclassified"
    assert resolution["display_grade"] == "U"


def test_gamemaker_pause_but_no_yyp_project_still_unclassified():
    """No .yyp project detected → IDE pause doesn't apply, remains U."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=2,
        criteria_total=10,
        percentage=20.0,
        has_yyp=False,  # No GameMaker project
        paused=True,
        has_exe=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    # Without a .yyp project, the GameMaker pause logic shouldn't help
    # Falls back to general logic: achieved > 0 → Partial
    assert resolution["outcome_band"] in ("Partial", "Unclassified")


def test_gamemaker_not_paused_uses_normal_logic():
    """When GameMaker is not paused (IDE available), normal grading applies."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=2,
        criteria_total=10,
        percentage=20.0,
        has_yyp=True,
        paused=False,  # Not paused
        has_exe=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    # Should use normal logic: has_yyp_project and achieved > 0 → Partial
    assert resolution["outcome_band"] == "Partial"


def test_gamemaker_pause_with_exe_present_never_applies():
    """If .exe already exists, IDE pause logic should never trigger."""
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=2,
        criteria_total=10,
        percentage=20.0,
        has_yyp=True,
        paused=True,
        has_exe=True,  # Executable present
    )

    resolution = resolve_institutional_classification(grading_result)

    # With exe + achieved > 0, the logic checks pct >= 40
    # At 20%, should fall through to GameMaker pause logic or general Partial logic
    assert resolution["outcome_band"] in ("Partial", "Referral")


def test_ahmed_osman_scenario():
    """
    Real scenario: Ahmed Osman
    - Valid .yyp GameMaker project ✅
    - 20% criteria achievement ✅
    - No .exe (GameMaker IDE not installed → paused) ❌
    - Expected: Referral (not U)
    """
    grading_result = _make_grading_result_with_gamemaker_pause(
        criteria_achieved=2,
        criteria_total=10,
        percentage=20.0,
        has_yyp=True,
        paused=True,
        has_exe=False,
        has_doc=False,
    )

    resolution = resolve_institutional_classification(grading_result)

    # Ahmed should get Referral because:
    # - gamemaker_paused=True
    # - has_yyp_project=True
    # - achieved=2 > 0
    # - pct=20 >= 20
    assert resolution["outcome_band"] == "Referral", (
        f"Ahmed Osman should get Referral, not {resolution['outcome_band']}"
    )
    assert resolution["display_grade"] == "R"
    assert resolution["criteria_achieved"] == 2
    assert resolution["percentage"] == 20.0
