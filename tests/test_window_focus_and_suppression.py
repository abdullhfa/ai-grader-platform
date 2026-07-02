from __future__ import annotations

from app.academic_explainability import build_missing_evidence_diagnostics
from app.pro_btec_pearson import build_criteria_breakdown_for_ui
from app.runtime_screenshot_validation import validate_runtime_screenshot_record
from app.window_focus_manager import classify_capture_scope


def test_classify_capture_scope_prefers_game_window():
    bbox = (100, 100, 1200, 800)
    assert classify_capture_scope(capture_bbox=bbox, game_bbox=bbox) == "game_window"
    assert classify_capture_scope(capture_bbox=bbox, game_bbox=None) == "desktop_fallback"


def test_text_suppression_blocks_runtime_without_l5():
    inv = {
        "documentation": {"status": "analyzed", "files": [{"name": "r.docx", "ext": ".docx"}]},
        "source_code": {"status": "detected", "files": [{"name": "main.gd", "ext": ".gd"}]},
        "executable_artifacts": {"files": [{"name": "game.exe"}], "runtime_verified": True},
        "runtime_artifacts": {"executables_detected": True},
        "embedded_screenshots": {"count": 3},
        "runtime_observation_report": {
            "status": "completed",
            "runtime_verified": True,
            "runtime_observed": True,
            "mechanics_verification": {"mechanics_level": "L3"},
        },
        "l5_human_playtest": {"pass": False},
    }
    diag = build_missing_evidence_diagnostics(inv, grading_mode="pro")
    rows = {r["requirement_ar"]: r for r in diag["rows"]}
    assert rows["التحقق من التشغيل (runtime)"]["present"] is False
    assert "بدون L5" in rows["التحقق من التشغيل (runtime)"]["status_ar"]


def test_reject_non_game_window_screenshot():
    shot = validate_runtime_screenshot_record(
        {
            "status": "captured",
            "capture_scope": "desktop_fallback",
            "game_window_detected": False,
        }
    )
    assert shot["status"] == "rejected"


def test_criteria_breakdown_partial_when_achieved_not_awardable():
    rows = build_criteria_breakdown_for_ui(
        {
            "criteria_results": [
                {
                    "criteria_level": "8/B.M2",
                    "achieved": True,
                    "awardable": False,
                    "award_block_reason_ar": "لم يحقق جميع معايير Pass",
                    "score": 70,
                }
            ]
        }
    )
    assert rows[0]["achieved_display_ar"] == "جزئي — محجوب"
    assert rows[0]["awardable_display_ar"] == "لا"


def test_criteria_breakdown_prerequisite_reason_for_m2():
    rows = build_criteria_breakdown_for_ui(
        {
            "criteria_results": [
                {
                    "criteria_level": "8/B.M2",
                    "achieved": True,
                    "awardable": False,
                    "award_block_reason": "missing_pass_criteria",
                    "score": 70,
                }
            ]
        }
    )
    assert rows[0]["achieved_display_ar"] == "جزئي — محجوب (Prerequisite)"
    assert "C.P5/C.P6" in rows[0]["gate_reason_ar"]
