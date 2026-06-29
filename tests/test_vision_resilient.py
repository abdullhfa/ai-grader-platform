"""Vision resilient analysis — empty response handling and batch split."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.ai_provider import AIProvider, EmptyVisionResponse, merge_vision_lane_results


def _provider() -> AIProvider:
    p = AIProvider.__new__(AIProvider)
    p.provider = "gemini"
    p.model = "test-model"
    p.client = MagicMock()
    return p


def test_analyze_images_resilient_full_batch_success():
    prov = _provider()
    images = [(b"x", "image/png")] * 3
    with patch.object(prov, "_openai_analyze_images", return_value="ok analysis"):
        out = prov.analyze_images_resilient(images, context="ctx")
    assert out["vision_completed"] is True
    assert out["images_submitted"] == 3
    assert out["images_analyzed"] == 3
    assert out["text"] == "ok analysis"
    assert out["vision_error"] == ""


def test_analyze_images_resilient_records_failed_after_empty():
    prov = _provider()
    images = [(b"x", "image/png")] * 2

    def _empty(*_a, **_k):
        raise EmptyVisionResponse("empty_vision_response")

    with patch.object(prov, "_openai_analyze_images", side_effect=_empty):
        out = prov.analyze_images_resilient(images, context="ctx")
    assert out["vision_attempted"] is True
    assert out["vision_completed"] is False
    assert out["vision_error"] == "empty_vision_response"
    assert out["images_analyzed"] == 0
    assert out["images_submitted"] == 2


def test_analyze_images_resilient_splits_after_full_failure():
    prov = _provider()
    images = [(b"x", "image/png")] * 6
    calls = {"n": 0}

    def _side_effect(batch, prompt, temperature):
        calls["n"] += 1
        if len(batch) == 6:
            raise EmptyVisionResponse("empty_vision_response")
        if len(batch) == 1:
            return f"batch-{calls['n']}"
        raise EmptyVisionResponse("empty_vision_response")

    with patch.object(prov, "_openai_analyze_images", side_effect=_side_effect):
        out = prov.analyze_images_resilient(images, context="ctx", batch_size=1)
    assert out["vision_completed"] is True
    assert out["images_analyzed"] == 6
    assert len(out["vision_batches"]) == 6


def test_merge_vision_lane_results_independent_lanes():
    word = {
        "text": "docx analysis",
        "images_submitted": 10,
        "images_analyzed": 10,
        "vision_attempted": True,
        "vision_completed": True,
        "vision_error": "",
        "vision_batches": [{"submitted": 10, "analyzed": 10, "error": None}],
    }
    video = {
        "text": "video kf analysis",
        "images_submitted": 5,
        "images_analyzed": 5,
        "vision_attempted": True,
        "vision_completed": True,
        "vision_error": "",
        "vision_batches": [{"submitted": 5, "analyzed": 5, "error": None}],
    }
    merged = merge_vision_lane_results(word, video)
    assert merged["images_submitted"] == 15
    assert merged["images_analyzed"] == 15
    assert merged["vision_completed"] is True
    assert "docx analysis" in merged["text"]
    assert "video kf analysis" in merged["text"]
    assert merged["vision_batches"][0]["lane"] == "docx_embedded"
    assert merged["vision_batches"][-1]["lane"] == "video_keyframe"
