"""Tests for requirement checklist extraction."""
from app.requirement_checklist import build_requirement_checklist
from app.requirement_extractor import RequirementExtractor


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


def test_arabic_negated_jump_is_not_a_requirement():
    text = "لا يمكن القفز فوق الأعداء، وحققت النسخة الجديدة قفزة نوعية في رضا المستخدمين."

    out = build_requirement_checklist(student_text=text)

    jump = next(row for row in out["requirements"] if row["id"] == "jump")
    assert "jump" not in out["requirement_ids"]
    assert jump["mentioned_in_sources"] is False
    assert jump["applicability"] == "not_applicable"


def test_explicit_jump_requirement_wins_when_text_also_mentions_a_limitation():
    text = "يمكن للاعب القفز، لكنه لا يمكنه القفز فوق الجدار الأخير."

    out = build_requirement_checklist(student_text=text)

    jump = next(row for row in out["requirements"] if row["id"] == "jump")
    assert "jump" in out["requirement_ids"]
    assert jump["applicability"] == "required"


def test_explicitly_absent_jump_is_removed_from_runtime_plan():
    plan = RequirementExtractor().extract(
        engine="godot",
        student_text="لعبة حركة علوية؛ لا يمكن للاعب القفز.",
        document_paths=["gdd.docx"],
    )

    assert "player_jump" not in plan.requirement_ids()
