"""LLM JSON repair — bracket typo from Ollama/Qwen."""
from __future__ import annotations

from app.llm_json_utils import parse_llm_grading_json


def test_repair_reasoning_bracket_typo():
    # Keep this regression deterministic; recent_grade_response.txt contains
    # the most recent student's real verdict and legitimately changes.
    sample = '''```json
{
  "criteria_evaluation": {
    "8/BC.D2": {"achieved": true, "score": 75, "evidence": "x", "reasoning": "نص عربي."]
  },
  "overall_feedback": "ملخص",
  "strengths": ["قوة"],
  "improvements": ["تحسين"]
}
```'''

    parsed = parse_llm_grading_json(sample)
    assert "criteria_evaluation" in parsed
    assert parsed["criteria_evaluation"]["8/BC.D2"]["achieved"] is True
    assert isinstance(parsed.get("strengths"), list)


def test_repair_missing_opening_quote_on_criterion_key():
    """Regression for the malformed Gemini response seen in batch grading."""
    sample = '''```json
{
  "criteria_evaluation": {
    "8/C.P6": {"achieved": false},
    C.P7": {"achieved": true, "reasoning": "تمت المراجعة"},
    unquoted_key: {"achieved": false}
  },
  "overall_feedback": "ملخص"
}
```'''

    parsed = parse_llm_grading_json(sample)

    assert parsed["criteria_evaluation"]["C.P7"]["achieved"] is True
    assert parsed["criteria_evaluation"]["unquoted_key"]["achieved"] is False
