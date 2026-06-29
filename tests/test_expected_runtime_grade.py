"""Tests for advisory expected runtime grade display."""
from __future__ import annotations

from app.expected_runtime_grade import (
    EXPECTED_RUNTIME_DISCLAIMER_AR,
    build_expected_runtime_grade_display,
    build_counterfactual_criteria,
)


def _ahmed_like_snapshot() -> dict:
    criteria = [
        {"criteria_level": "8/B.P3", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/B.P4", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/C.P5", "achieved": False, "verdict_status": "inconclusive"},
        {"criteria_level": "8/C.P6", "achieved": False, "verdict_status": "inconclusive"},
        {"criteria_level": "8/C.P7", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/B.M2", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/C.M3", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/BC.D2", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/BC.D3", "achieved": True, "verdict_status": "pass"},
    ]
    return {
        "grade_level": "U",
        "grading_mode": "fast",
        "execution_mode": "BASIC",
        "criteria_results": criteria,
        "criterion_authority": [
            {
                "criterion": "8/C.P5",
                "decision_basis": "inconclusive_no_runtime",
                "result": "INCONCLUSIVE",
            },
            {
                "criterion": "8/C.P6",
                "decision_basis": "inconclusive_no_structured_test_plan",
                "testing_authority_available": True,
                "result": "INCONCLUSIVE",
            },
        ],
        "visual_evidence_summary": {
            "images_analyzed": 20,
            "video_keyframes_analyzed": 10,
            "runtime_verified": False,
        },
        "artifact_inventory": {
            "source_code": {"status": "analyzed", "files": [{"name": "game_manager.gd"}]},
            "runtime_observation_report": {"status": "skipped_fast_mode"},
        },
        "basic_video_keyframes_meta": {"frames_extracted": 10, "videos_found": 2},
    }


def test_expected_shown_when_runtime_flip_but_grade_unchanged():
    snap = _ahmed_like_snapshot()
    for row in snap["criteria_results"]:
        if row["criteria_level"] == "8/B.P4":
            row["achieved"] = False
            row["verdict_status"] = "fail"
    out = build_expected_runtime_grade_display(snap)
    assert out is not None
    assert out["expected_btec_grade"] == "U"
    assert out["grade_unchanged"] is True
    assert "8/C.P5" in out["criteria_flipped_advisory"]


def test_expected_grade_u_to_d_for_ahmed_like():
    out = build_expected_runtime_grade_display(_ahmed_like_snapshot())
    assert out is not None
    assert out["official_btec_grade"] == "U"
    assert out["expected_btec_grade"] == "D"
    assert "التقدير المعتمد" in out["official_grade_label_ar"]
    assert "التقدير المتوقع" in out["expected_grade_label_ar"]
    assert out["disclaimer_ar"] == EXPECTED_RUNTIME_DISCLAIMER_AR


def test_counterfactual_flips_p5_and_p6():
    snap = _ahmed_like_snapshot()
    cf = build_counterfactual_criteria(snap["criteria_results"], snap)
    by_level = {r["criteria_level"]: r for r in cf}
    assert by_level["8/C.P5"]["achieved"] is True
    assert by_level["8/C.P6"]["achieved"] is True


def test_no_expected_block_when_runtime_verified():
    snap = _ahmed_like_snapshot()
    snap["artifact_inventory"]["runtime_observation_report"] = {"runtime_verified": True}
    assert build_expected_runtime_grade_display(snap) is None


def test_p6_hard_fail_without_testing_docs_not_flipped():
    snap = _ahmed_like_snapshot()
    for row in snap["criteria_results"]:
        if row["criteria_level"] == "8/C.P6":
            row["verdict_status"] = "fail"
    for row in snap["criterion_authority"]:
        if row["criterion"] == "8/C.P6":
            row["testing_authority_available"] = False
            row["decision_basis"] = "none"
            row["result"] = "FAIL"
    out = build_expected_runtime_grade_display(snap)
    assert out is not None
    assert "8/C.P5" in out["criteria_flipped_advisory"]
    assert "8/C.P6" not in out["criteria_flipped_advisory"]
    assert out["expected_btec_grade"] == "U"


def test_expected_p7_inconclusive_flips_to_d():
    snap = _ahmed_like_snapshot()
    for row in snap["criteria_results"]:
        if row["criteria_level"] == "8/C.P7":
            row["achieved"] = False
            row["verdict_status"] = "inconclusive"
    snap["criterion_authority"].append(
        {
            "criterion": "8/C.P7",
            "decision_basis": "inconclusive_no_runtime",
            "result": "INCONCLUSIVE",
        }
    )
    out = build_expected_runtime_grade_display(snap)
    assert out is not None
    assert out["expected_btec_grade"] == "D"
    assert "8/C.P7" in out["criteria_flipped_advisory"]
    assert out["missing_pass_after_runtime_flip"] == []


def test_qasim_like_hard_fail_p5_p6_expected_u_not_d():
    """P5/P6 FAIL (no test docs) + M/D achieved — expected must stay U, not D."""
    criteria = [
        {"criteria_level": "8/B.P3", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/B.P4", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/C.P5", "achieved": False, "verdict_status": "fail"},
        {"criteria_level": "8/C.P6", "achieved": False, "verdict_status": "fail"},
        {"criteria_level": "8/C.P7", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/B.M2", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/C.M3", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/BC.D2", "achieved": True, "verdict_status": "pass"},
        {"criteria_level": "8/BC.D3", "achieved": True, "verdict_status": "pass"},
    ]
    snap = {
        "grade_level": "U",
        "grading_mode": "fast",
        "execution_mode": "BASIC",
        "criteria_results": criteria,
        "criterion_authority": [
            {"criterion": "8/C.P5", "decision_basis": "none", "result": "FAIL"},
            {"criterion": "8/C.P6", "decision_basis": "none", "result": "FAIL"},
        ],
        "visual_evidence_summary": {"images_analyzed": 5, "runtime_verified": False},
        "artifact_inventory": {
            "source_code": {"status": "analyzed", "files": [{"name": "player.gml"}]},
        },
    }
    out = build_expected_runtime_grade_display(snap)
    assert out is not None
    assert out["expected_btec_grade"] == "U"
