"""LLM JSON repair — bracket typo from Ollama/Qwen."""
from __future__ import annotations

from pathlib import Path

from app.llm_json_utils import parse_llm_grading_json


def test_repair_reasoning_bracket_typo():
    raw_path = Path(__file__).resolve().parents[1] / "recent_grade_response.txt"
    if not raw_path.is_file():
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
    else:
        sample = raw_path.read_text(encoding="utf-8")

    parsed = parse_llm_grading_json(sample)
    assert "criteria_evaluation" in parsed
    assert parsed["criteria_evaluation"]["8/BC.D2"]["achieved"] is True
    assert isinstance(parsed.get("strengths"), list)
