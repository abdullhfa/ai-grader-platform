"""Tests for deterministic B.P3 / B.P4 design evidence assessor."""
from __future__ import annotations

from app.design_evidence_assessor import (
    build_design_evidence_bundle,
    evaluate_bp3_deterministic,
    evaluate_bp4_deterministic,
    is_b_band_criterion,
    try_evaluate_design_criterion,
)

_AHMAD_CORPUS = """
Game Design Document (GDD) for fruit collection game.
Mechanics: player movement, score system, timer, health.
Level design includes multiple stages with increasing difficulty.
HUD shows score and time left. Controls: WASD and space to jump.
UI menu screen and win/loss screens documented.
User testing questionnaire collected feedback from 5 players.
Functional test plan with expected results documented.
Godot source includes game_manager.gd and area_2d scenes.
"""


def test_is_b_band_criterion():
    assert is_b_band_criterion("B.P3", "P3", "P3")
    assert is_b_band_criterion("B.P4", "P4", "P4")
    assert not is_b_band_criterion("C.P4", "P4", "P4")


def test_bp3_passes_with_gdd_and_ui_screens():
    inv = {
        "documentation": {"status": "analyzed", "files": [{"name": "هدف ب.docx"}]},
        "embedded_screenshots": {"count": 5},
        "testing_evidence": {"status": "partial"},
    }
    bundle = build_design_evidence_bundle(
        corpus=_AHMAD_CORPUS, artifact_inventory=inv, execution_mode="PRO"
    )
    achieved, score, reason, verdict, _found = evaluate_bp3_deterministic(
        bundle, criteria_level="B.P3", execution_mode="PRO"
    )
    assert bundle.bp3_score >= 2
    assert achieved is True
    assert verdict == "pass"
    assert score == 70


def test_bp3_fails_with_exe_only():
    bundle = build_design_evidence_bundle(
        corpus="P_03.exe launched successfully.",
        artifact_inventory={"executable_artifacts": {"files": ["P_03.exe"]}},
        execution_mode="PRO",
    )
    achieved, _score, _reason, verdict, _ = evaluate_bp3_deterministic(
        bundle, criteria_level="B.P3", execution_mode="PRO"
    )
    assert achieved is False
    assert verdict == "fail"


def test_bp4_passes_with_survey_only_pro():
    inv = {"testing_evidence": {"status": "partial"}}
    bundle = build_design_evidence_bundle(
        corpus="Questionnaire results from user testing survey.",
        artifact_inventory=inv,
        execution_mode="PRO",
    )
    achieved, score, _reason, verdict, _ = evaluate_bp4_deterministic(
        bundle, criteria_level="B.P4", execution_mode="PRO"
    )
    assert achieved is True
    assert verdict == "pass"
    assert score == 70


def test_bp4_not_peer_review_rule():
    row = try_evaluate_design_criterion(
        criteria_level="B.P4",
        corpus=_AHMAD_CORPUS,
        artifact_inventory={
            "documentation": {"status": "analyzed"},
            "embedded_screenshots": {"count": 4},
            "testing_evidence": {"status": "partial"},
        },
        execution_mode="PRO",
    )
    assert row is not None
    assert row["rule_id"] == "visual_design_rule_v1"
    assert row["authority"] == "VISUAL_DESIGN_RULE_V1"
    assert row["deterministic_achieved"] is True


def test_bp4_standard_requires_two_signals():
    bundle = build_design_evidence_bundle(
        corpus="survey questionnaire only",
        artifact_inventory={"testing_evidence": {"status": "partial"}},
        execution_mode="STANDARD",
    )
    achieved, _score, _reason, verdict, _ = evaluate_bp4_deterministic(
        bundle, criteria_level="B.P4", execution_mode="STANDARD"
    )
    assert achieved is False
    assert verdict == "inconclusive"


def test_ahmad_like_bundle_bp3_bp4_stable():
    inv = {
        "documentation": {"status": "analyzed", "file_count": 1},
        "embedded_screenshots": {"count": 20},
        "testing_evidence": {"status": "partial"},
        "visual_verification": {"screenshots_analyzed": 17},
    }
    for _ in range(2):
        bp3 = try_evaluate_design_criterion(
            criteria_level="B.P3",
            corpus=_AHMAD_CORPUS,
            artifact_inventory=inv,
            execution_mode="PRO",
        )
        bp4 = try_evaluate_design_criterion(
            criteria_level="B.P4",
            corpus=_AHMAD_CORPUS,
            artifact_inventory=inv,
            execution_mode="PRO",
        )
        assert bp3["deterministic_achieved"] is True
        assert bp4["deterministic_achieved"] is True
