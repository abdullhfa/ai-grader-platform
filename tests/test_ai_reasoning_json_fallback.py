"""Unit tests for Gemini/OpenRouter reasoning-only JSON detection."""

from app.ai_provider import _text_looks_like_json_object


def test_json_object_detected():
    assert _text_looks_like_json_object('{"criteria_evaluation": {}}')
    assert _text_looks_like_json_object('```json\n{"a":1}\n```')


def test_markdown_cot_not_json():
    cot = (
        "**Evaluating Student Work**\n\n"
        "I am currently focused on evaluating the student's submission."
    )
    assert not _text_looks_like_json_object(cot)
    assert not _text_looks_like_json_object("")
    assert not _text_looks_like_json_object("Expecting value")
