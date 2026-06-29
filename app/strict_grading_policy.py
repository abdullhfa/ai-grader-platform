"""
Strict deterministic grading policy — reproducible results from file content only.

When enabled (default):
- No GradingCache lookup/save for criterion grades or AI detection scores
- AI likelihood uses deterministic text metrics only (no LLM variance)
- Rule/deterministic engines override AI on CLEAR_FAIL only (BORDERLINE → AI decides)
- Plagiarism is always recomputed; stored rows are not reused as scores
"""
from __future__ import annotations

import os
from typing import Any, Dict


def strict_deterministic_enabled() -> bool:
    val = os.environ.get("AI_GRADER_STRICT_DETERMINISTIC", "1").strip().lower()
    return val not in ("0", "false", "no", "off")


def skip_grading_cache_default() -> bool:
    """Grading cache bypass — same files must yield fresh rule+AI merge every run."""
    return strict_deterministic_enabled()


def use_deterministic_ai_detection_only() -> bool:
    """Metrics-only AI % — opt-in via AI_DETECTION_DETERMINISTIC_ONLY when strict is on."""
    if not strict_deterministic_enabled():
        return False
    val = os.environ.get("AI_DETECTION_DETERMINISTIC_ONLY", "0").strip().lower()
    return val in ("1", "true", "yes", "on")


def persist_grading_cache() -> bool:
    return not strict_deterministic_enabled()


def persist_ai_detection_cache() -> bool:
    return not strict_deterministic_enabled()


def reuse_plagiarism_db_scores() -> bool:
    return not strict_deterministic_enabled()
