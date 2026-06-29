"""Tests for strict deterministic grading policy."""
from app.graders.hybrid_grader import HybridGrader
from app.rubric.deterministic_engine import merge_deterministic_with_ai
from app.strict_grading_policy import (
    skip_grading_cache_default,
    strict_deterministic_enabled,
    use_deterministic_ai_detection_only,
)


def test_strict_mode_enabled_by_default():
    assert strict_deterministic_enabled() is True
    assert skip_grading_cache_default() is True
    assert use_deterministic_ai_detection_only() is False


def test_hybrid_strict_clear_fail_overrides_ai():
    ai_eval = {"achieved": True, "score": 85, "feedback": "ok"}
    rule_results = {
        "B.P3": {
            "verdict": "CLEAR_FAIL",
            "confidence": 0.1,
            "evidence": {"verb_count": 0, "domain_count": 0},
        }
    }
    merged = HybridGrader.merge_results({"B.P3": ai_eval}, rule_results)
    assert merged["B.P3"]["achieved"] is False
    assert merged["B.P3"].get("achievement_authority") == "RULE_STRICT"


def test_hybrid_strict_borderline_trusts_ai():
    ai_eval = {"achieved": True, "score": 70}
    rule_results = {
        "C.P5": {
            "verdict": "BORDERLINE",
            "confidence": 0.45,
            "evidence": {"verb_count": 2, "domain_count": 1},
        }
    }
    merged = HybridGrader.merge_results({"C.P5": ai_eval}, rule_results)
    assert merged["C.P5"]["achieved"] is True


def test_deterministic_merge_enforces_in_strict_mode():
    grading = {
        "criteria_results": [
            {"criteria_level": "C.P6", "achieved": True, "score": 90},
        ],
        "student_text": "sample",
    }
    rows = [
        {
            "criteria_level": "C.P6",
            "deterministic_achieved": False,
            "deterministic_score": 0,
            "authority": "DETERMINISTIC",
            "reason": "no_test_evidence",
        }
    ]
    out = merge_deterministic_with_ai(grading, rows)
    cr = out["criteria_results"][0]
    assert cr["achieved"] is False
    assert cr["achievement_authority"] == "DETERMINISTIC"
