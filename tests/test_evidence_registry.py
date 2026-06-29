"""Tests for Evidence Registry + deterministic rubric v2."""
from __future__ import annotations

from app.evidence_registry import build_grade_display_metrics, find_evidence_snippets
from app.rubric.deterministic_engine import (
    RUBRIC_ENGINE_VERSION,
    evaluate_criterion_deterministic,
    merge_deterministic_with_ai,
    run_deterministic_rubric,
)
import re


def test_peer_review_survey_arabic_pass():
    text = (
        "تطوير اللعبة بناءً على نتائج الاستبيان. "
        + "x" * 300
    )
    row = evaluate_criterion_deterministic(
        criteria_level="8/B.P4",
        criteria_description="peer review",
        student_text=text,
        execution_mode="PRO",
    )
    assert row["deterministic_achieved"] is True
    assert row["rule_id"] == "questionnaire_or_survey"
    assert row["evidence_registry"]["result"] == "pass"
    assert any("استبيان" in e.get("rule_key", "") for e in row["evidence_registry"]["evidence_found"])


def test_cp5_basic_inconclusive_not_hard_fail_label():
    text = "class Player extends Node\n" + ("def move(): pass\n" * 20)
    row = evaluate_criterion_deterministic(
        criteria_level="8/C.P5",
        criteria_description="produce game",
        student_text=text,
        runtime_validation={"functional_smoke": {"functional_smoke_pass": None, "reason": "status_skipped"}},
        execution_mode="BASIC",
    )
    assert row["verdict_status"] == "inconclusive"
    assert row["deterministic_achieved"] is False
    assert row["authority"] == "DETERMINISTIC_INCONCLUSIVE"
    assert row["execution_mode"] == "BASIC"


def test_cp6_testing_phase_pattern():
    text = "مرحلة الاختبار في لوحة العمل " + ("اختبار " * 50)
    row = evaluate_criterion_deterministic(
        criteria_level="8/C.P6",
        criteria_description="testing",
        student_text=text,
        runtime_validation={"functional_smoke": {"functional_smoke_pass": None, "reason": "status_skipped"}},
        execution_mode="BASIC",
    )
    assert row["verdict_status"] == "inconclusive"
    assert row["rule_id"] == "test_doc_runtime_inconclusive"


def test_grade_display_metrics_separates_btec_and_criteria_score():
    grading = {
        "grade_level": "U",
        "criteria_score_pct": 78,
        "percentage": 78,
        "ai_likelihood": 15.6,
        "ai_detection_info": {"score": 15.6},
        "criteria_results": [
            {"criteria_level": "8/B.P3", "achieved": True},
            {"criteria_level": "8/B.P4", "achieved": False},
            {"criteria_level": "8/BC.D3", "achieved": True},
        ],
        "execution_mode": "BASIC",
    }
    gdm = build_grade_display_metrics(grading)
    assert gdm["final_btec_grade"] == "U"
    assert gdm["highest_criterion_achieved"] == "8/BC.D3"
    assert gdm["criteria_score_pct"] == 78
    assert gdm["criteria_completion_pct"] == 78
    assert gdm["grade_score_divergence"] is True
    assert gdm["ai_risk_pct"] == 15.6


def test_grade_display_metrics_separates_btec_and_highest():
    grading = {
        "grade_level": "U",
        "percentage": 78,
        "ai_likelihood": 15.6,
        "ai_detection_info": {"score": 15.6},
        "criteria_results": [
            {"criteria_level": "8/B.P3", "achieved": True},
            {"criteria_level": "8/B.P4", "achieved": False},
            {"criteria_level": "8/BC.D3", "achieved": True},
        ],
        "execution_mode": "BASIC",
    }
    gdm = build_grade_display_metrics(grading)
    assert gdm["final_btec_grade"] == "U"
    assert gdm["highest_criterion_achieved"] == "8/BC.D3"
    assert gdm["criteria_completion_pct"] == 78
    assert gdm["ai_risk_pct"] == 15.6


def test_run_deterministic_rubric_attaches_registry():
    grading = {
        "criteria_results": [
            {"criteria_level": "8/B.P4", "achieved": False, "score": 0, "feedback": "ai"},
        ],
        "student_text": "نتائج الاستبيان " + "x" * 300,
    }
    criteria = [{"criteria_level": "8/B.P4", "criteria_description": "peer review"}]
    out = run_deterministic_rubric(
        grading,
        grading_criteria=criteria,
        student_text=grading["student_text"],
        grading_mode="deep",
    )
    assert out["evidence_registry"]["rule_version"]
    assert out["grade_display_metrics"]["final_btec_grade"]
    assert out["deterministic_rubric_engine"]["version"] == RUBRIC_ENGINE_VERSION
    assert out["criteria_results"][0]["achieved"] is True


def test_find_evidence_snippets_efficient():
    text = "survey results and questionnaire"
    found, missing = find_evidence_snippets(
        text,
        rule_id="test",
        patterns=[
            ("survey", re.compile(r"survey", re.I)),
            ("questionnaire", re.compile(r"questionnaire", re.I)),
        ],
    )
    assert len(found) == 2
    assert not missing
