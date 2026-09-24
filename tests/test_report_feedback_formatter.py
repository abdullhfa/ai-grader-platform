"""Tests for Word report display helpers."""
from __future__ import annotations

from app.report_feedback_formatter import (
    build_godot_runtime_outcome,
    criterion_report_display,
    format_criterion_feedback_for_report,
    format_godot_runtime_outcome_ar,
)


def test_criterion_report_display_blocked_merit():
    icon, text, bg, bd = criterion_report_display(
        {"achieved": True, "awardable": False}
    )
    assert icon == "⏸"
    assert text.startswith("محجوب")
    assert "تحقق المعيار" not in text.split("—")[0]
    assert bg == "FEF3C7"


def test_format_feedback_institutional_only_when_not_achieved():
    fb = format_criterion_feedback_for_report(
        "تم تحقيق المعيار بشكل ممتاز.",
        achieved=False,
    )
    assert "قرار الحوكمة" in fb
    assert "تعليق المقيّم" not in fb


def test_godot_runtime_outcome_structured_sections():
    outcome = build_godot_runtime_outcome(
        {
            "gameplay_entered": False,
            "failure_reason_code": "MENU_NOT_RESOLVED",
            "failure_reason_ar": "قائمة/start screen لم تُحل إلى gameplay.",
            "l4_level": "L3",
            "menu_navigation": {"status": "menu_stuck"},
        },
        {"criterion_pass": {"P5": False, "P6": False}},
        agent_play_label_ar="لا — MENU_NOT_RESOLVED",
    )
    text = format_godot_runtime_outcome_ar(outcome)
    assert "نتيجة تشغيل اللعبة" in text
    assert "سبب عدم اكتمال التشغيل" in text or "سبب الفشل النهائي" in text
    assert "تفاصيل تقنية" in text or "ملخص الأدلة" in text
    assert "C.P5" in text and "C.P6" in text
    assert "MENU_NOT_RESOLVED" in text
    assert outcome["criterion_pass_p5"] is False


def test_format_feedback_includes_godot_block():
    outcome = build_godot_runtime_outcome(
        {"failure_reason_code": "BOOT_TIMEOUT", "failure_reason_ar": "انتهت مهلة الإقلاع"},
        {"criterion_pass": {"P5": False, "P6": False}},
    )
    fb = format_criterion_feedback_for_report(
        "تعليق المقيّم.",
        godot_runtime_outcome=outcome,
    )
    assert "BOOT_TIMEOUT" in fb or "انتهت مهلة الإقلاع" in fb
    assert "C.P5" in fb
