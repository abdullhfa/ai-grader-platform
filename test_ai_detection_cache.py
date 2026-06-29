"""AI detection cache key stability."""
from __future__ import annotations

from app.batch_grader import build_ai_detection_cache_key


def test_ai_detection_cache_key_stable_for_same_text():
    text = "هذا نص طالب ثابت للاختبار " * 40
    k1 = build_ai_detection_cache_key(core_text=text)
    k2 = build_ai_detection_cache_key(core_text=text)
    assert k1 == k2
    assert k1.startswith("ai_det:v1:text:")


def test_ai_detection_cache_key_differs_for_different_text():
    k1 = build_ai_detection_cache_key(core_text="نص أ")
    k2 = build_ai_detection_cache_key(core_text="نص ب")
    assert k1 != k2
