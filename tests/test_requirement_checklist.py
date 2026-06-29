"""Tests for requirement checklist extraction."""
from app.requirement_checklist import build_requirement_checklist


def test_extracts_jump_and_movement_from_gdd_text():
    text = "The player can jump and move left/right. Collect coins for score."
    out = build_requirement_checklist(student_text=text)
    ids = set(out["requirement_ids"])
    assert "jump" in ids
    assert "player_movement" in ids
    assert "collect_items" in ids


def test_arabic_requirements_detected():
    text = "يمكن للاعب القفز وجمع العملات مع نظام النقاط"
    out = build_requirement_checklist(student_text=text)
    ids = set(out["requirement_ids"])
    assert "jump" in ids
    assert "collect_items" in ids
