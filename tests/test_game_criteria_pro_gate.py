"""C.P5 / C.P6 / C.P7 require PRO (game runtime) in BASIC mode."""
from __future__ import annotations

from app.visual_evidence_registry import (
    GAME_CRITERIA_PRO_REASON_AR,
    apply_game_criteria_pro_gate,
    criterion_evidence_class,
    is_game_runtime_pro_criterion,
)


def test_p7_classified_as_game_dependent():
    assert criterion_evidence_class("8/C.P7", "present game to peers") == "visual_dependent"
    assert is_game_runtime_pro_criterion("8/C.P7") is True


def test_pro_gate_preserves_p7_achieved_in_basic():
    """P7 already achieved is not demoted; P5/P6 still gated."""
    snap = {
        "grading_mode": "fast",
        "execution_mode": "BASIC",
        "artifact_inventory": {
            "runtime_observation_report": {"status": "skipped_fast_mode"},
        },
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": False, "verdict_status": "inconclusive"},
            {"criteria_level": "8/C.P6", "achieved": False, "verdict_status": "inconclusive"},
            {"criteria_level": "8/C.P7", "achieved": True, "verdict_status": "pass", "score": 80},
        ],
    }
    out = apply_game_criteria_pro_gate(snap, grading_mode="fast")
    p7 = next(r for r in out["criteria_results"] if r["criteria_level"] == "8/C.P7")
    assert p7["achieved"] is True
    assert p7["verdict_status"] == "pass"
    assert out["game_criteria_pro_gate"]["applied"] is False


def test_pro_gate_converts_p6_fail_to_inconclusive():
    snap = {
        "grading_mode": "fast",
        "artifact_inventory": {
            "runtime_observation_report": {"status": "skipped_fast_mode"},
        },
        "criteria_results": [
            {"criteria_level": "8/C.P6", "achieved": False, "verdict_status": "fail", "score": 0},
            {"criteria_level": "8/C.P7", "achieved": False, "verdict_status": "fail", "score": 0},
        ],
    }
    out = apply_game_criteria_pro_gate(snap, grading_mode="fast")
    p6 = next(r for r in out["criteria_results"] if r["criteria_level"] == "8/C.P6")
    p7 = next(r for r in out["criteria_results"] if r["criteria_level"] == "8/C.P7")
    assert p6["verdict_status"] == "inconclusive"
    assert p6.get("pro_gate_converted_from_fail") is True
    assert p6["requires_pro"] is True
    assert p7["verdict_status"] == "fail"
    assert p7["requires_pro"] is True


def test_pro_gate_skipped_when_runtime_verified():
    snap = {
        "grading_mode": "fast",
        "artifact_inventory": {
            "runtime_observation_report": {"runtime_verified": True},
        },
        "criteria_results": [
            {"criteria_level": "8/C.P7", "achieved": True, "verdict_status": "pass"},
        ],
    }
    out = apply_game_criteria_pro_gate(snap, grading_mode="fast")
    p7 = out["criteria_results"][0]
    assert p7["achieved"] is True
    assert out.get("game_criteria_pro_gate") is None
