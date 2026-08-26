import json

from app.secondary_ai_review import run_secondary_review, select_sensitive_criteria


class FakeReviewer:
    provider = "deepseek"
    model = "fake-deepseek-review"

    def __init__(self, reviews=None, error=None):
        self.reviews = reviews or []
        self.error = error
        self.messages = None

    def chat_completion(self, messages, **kwargs):
        self.messages = messages
        if self.error:
            raise self.error
        return json.dumps({"criteria_reviews": self.reviews}, ensure_ascii=False)


def _result():
    return {
        "grade_level": "M",
        "primary_ai_grader": {"provider": "gemini", "model": "gemini-2.5-pro"},
        "criteria_results": [
            {"criteria_level": "A.P1", "achieved": True},
            {"criteria_level": "B.M1", "achieved": True},
            {"criteria_level": "BC.D2", "achieved": False, "runtime_gate_block": True},
        ],
    }


def _criteria():
    return [
        {"criteria_level": "A.P1", "criteria_description": "pass"},
        {"criteria_level": "B.M1", "criteria_description": "analyse"},
        {"criteria_level": "BC.D2", "criteria_description": "evaluate critically"},
    ]


def test_selector_reviews_sensitive_bands_and_gate_rows():
    selected = select_sensitive_criteria(_result())
    assert selected == ["B.M1", "BC.D2"]


def test_agreement_confirms_without_changing_authoritative_grade():
    result = _result()
    fake = FakeReviewer(
        [
            {"criterion": "M1", "achieved": True, "confidence": 0.9, "reasoning": "واضح"},
            {"criterion": "D2", "achieved": False, "confidence": 0.8, "reasoning": "ناقص"},
        ]
    )
    audit = run_secondary_review(
        result,
        student_text="student evidence",
        grading_criteria=_criteria(),
        reviewer_provider=fake,
        force_enabled=True,
    )
    assert audit["status"] == "CONFIRMED"
    assert result["grade_decision_status"] == "CONFIRMED_BY_SECONDARY_REVIEW"
    assert result["grade_level"] == "M"
    assert result["criteria_results"][2]["achieved"] is False
    # The independent reviewer is not anchored with Gemini's verdict or reasoning.
    prompt = fake.messages[1]["content"]
    assert "primary_ai_grader" not in prompt
    assert "authoritative_achieved" not in prompt


def test_disagreement_auto_resolves_to_primary_without_human_review(monkeypatch):
    monkeypatch.setenv("SECONDARY_REVIEW_DISAGREEMENT_POLICY", "primary")
    result = _result()
    fake = FakeReviewer(
        [
            {"criterion": "M1", "achieved": True, "confidence": 0.9, "reasoning": "متفق"},
            {"criterion": "D2", "achieved": True, "confidence": 0.8, "reasoning": "وجد تقييماً نقدياً"},
        ]
    )
    audit = run_secondary_review(
        result,
        student_text="student evidence",
        grading_criteria=_criteria(),
        reviewer_provider=fake,
        force_enabled=True,
    )
    assert audit["status"] == "AUTO_RESOLVED_PRIMARY"
    assert audit["hold_required"] is False
    assert result["grade_decision_status"] == "AUTO_RESOLVED_PRIMARY"
    assert result["human_review_required"] is False
    assert result["criteria_results"][2]["achieved"] is False
    assert result["criteria_results"][2]["secondary_review_auto_resolved"] == "primary"


def test_models_are_compared_to_each_other_not_to_later_rule_override():
    result = _result()
    result["criteria_results"][2]["primary_ai_decision"] = {"achieved": True}
    fake = FakeReviewer(
        [
            {"criterion": "M1", "achieved": True, "confidence": 0.9},
            {"criterion": "D2", "achieved": True, "confidence": 0.8},
        ]
    )
    audit = run_secondary_review(
        result,
        student_text="student evidence",
        grading_criteria=_criteria(),
        reviewer_provider=fake,
        force_enabled=True,
    )
    assert audit["disagreements"] == []
    assert [x["criterion"] for x in audit["deterministic_overrides"]] == ["BC.D2"]
    assert audit["status"] == "CONFIRMED_MODELS_WITH_RULE_OVERRIDE"


def test_reviewer_failure_is_transparent_and_keeps_primary_result():
    result = _result()
    audit = run_secondary_review(
        result,
        student_text="student evidence",
        grading_criteria=_criteria(),
        reviewer_provider=FakeReviewer(error=RuntimeError("offline")),
        force_enabled=True,
    )
    assert audit["status"] == "REVIEW_UNAVAILABLE"
    assert result["grade_decision_status"] == "PRIMARY_ONLY_REVIEW_UNAVAILABLE"
    assert result["grade_level"] == "M"
    assert result.get("human_review_required") is not True
