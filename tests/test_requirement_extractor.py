"""Tests for PRO requirement extraction and default playtest plan."""
from __future__ import annotations

from app.requirement_extractor import (
    DEFAULT_GODOT_EXE_PLAN,
    InputAction,
    RequirementExtractor,
    RequirementPlan,
    RequirementTest,
)


def test_requirement_extractor_default_plan():
    plan = RequirementExtractor().default_plan(submission_id="50", engine="godot")
    assert isinstance(plan, RequirementPlan)
    assert plan.submission_id == "50"
    assert plan.engine == "godot"
    ids = plan.requirement_ids()
    assert ids == [
        "menu_navigation",
        "player_movement",
        "player_jump",
        "score_system",
        "win_lose_condition",
    ]


def test_default_godot_exe_plan_structure():
    movement = next(r for r in DEFAULT_GODOT_EXE_PLAN.requirements if r.req_id == "player_movement")
    assert movement.btec_criteria == ["C.P5"]
    assert movement.verification_method == "pixel_shift_horizontal"
    assert movement.required_for_gate is True
    assert len(movement.input_sequence) == 2
    assert movement.input_sequence[0] == InputAction("key_hold", "d", duration=0.6)

    jump = next(r for r in DEFAULT_GODOT_EXE_PLAN.requirements if r.req_id == "player_jump")
    assert jump.verification_method == "pixel_shift_vertical"
    assert jump.btec_criteria == ["C.P5"]

    menu = next(r for r in DEFAULT_GODOT_EXE_PLAN.requirements if r.req_id == "menu_navigation")
    assert menu.required_for_gate is True
    assert menu.verification_method == "scene_change"


def test_extract_uses_default_when_no_documents():
    plan = RequirementExtractor().extract(submission_id="48", engine="exe")
    assert len(plan.requirements) == 5
    assert plan.extraction_confidence == 1.0


def test_extract_adds_optional_requirements_from_gdd_text():
    text = "Player collects coins and fights enemy opponents with score system."
    plan = RequirementExtractor().extract(
        submission_id="50",
        engine="godot",
        student_text=text,
        document_paths=["brief.docx"],
    )
    ids = set(plan.requirement_ids())
    assert "collect_items" in ids
    assert "enemy_interaction" in ids
    assert plan.extracted_from == ["brief.docx"]
    assert plan.extraction_confidence >= 0.85


def test_requirement_test_to_dict_roundtrip_fields():
    test = RequirementTest(
        req_id="player_movement",
        description="حركة اللاعب",
        btec_criteria=["C.P5"],
        input_sequence=[InputAction("key_hold", "d", duration=0.6)],
        verification_method="pixel_shift_horizontal",
        success_threshold=0.03,
        required_for_gate=True,
    )
    row = test.to_dict()
    assert row["req_id"] == "player_movement"
    assert row["input_sequence"][0]["action"] == "key_hold"
    assert row["input_sequence"][0]["key"] == "d"
