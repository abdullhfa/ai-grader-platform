"""Tests for Word report display helpers."""
from __future__ import annotations

from app.report_feedback_formatter import (
    criterion_report_display,
    format_criterion_feedback_for_report,
)


def test_criterion_report_display_blocked_merit():
    icon, text, bg, bd = criterion_report_display(
        {"achieved": True, "awardable": False}
    )
    assert icon == "⏸"
    assert "محجوب" in text
    assert bg == "FEF3C7"


def test_format_feedback_institutional_only_when_not_achieved():
    fb = format_criterion_feedback_for_report(
        "تم تحقيق المعيار بشكل ممتاز.",
        achieved=False,
    )
    assert "قرار الحوكمة" in fb
    assert "تعليق المقيّم" not in fb
