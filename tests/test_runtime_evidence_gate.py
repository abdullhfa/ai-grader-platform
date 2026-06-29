"""Runtime Evidence Gate — runtime-dependent criteria require real runtime evidence."""
from __future__ import annotations

from app.runtime_evidence_gate import (
    RUNTIME_GATED_SHORT,
    apply_runtime_evidence_gate,
    evaluate_runtime_evidence,
    is_game_submission,
)


def _game_criteria():
    return [
        {"criteria_level": "8/B.P3", "achieved": True, "awardable": True, "score": 80},
        {"criteria_level": "8/C.P5", "achieved": True, "awardable": True, "score": 80},
        {"criteria_level": "8/C.P6", "achieved": True, "awardable": True, "score": 80},
        {"criteria_level": "8/C.M3", "achieved": True, "awardable": True, "score": 80},
        {"criteria_level": "8/BC.D3", "achieved": True, "awardable": True, "score": 80},
    ]


def test_gated_set_matches_pearson_spec():
    assert RUNTIME_GATED_SHORT == frozenset({"P5", "P6", "M3", "D3"})


def test_non_game_submission_is_not_gated():
    gr = {
        "criteria_results": _game_criteria(),
        "submission_paths": ["essay.docx", "presentation.pptx"],
    }
    report = apply_runtime_evidence_gate(gr, artifact_inventory={})
    assert report["applied"] is False
    assert report["reason"] == "not_a_game_submission"
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    assert by["8/C.P5"]["achieved"] is True  # untouched


def test_scratch_without_runtime_evidence_blocks_gated_criteria():
    gr = {
        "criteria_results": _game_criteria(),
        "submission_paths": [
            r"uploads\bx48\game\Scrath file.sb3",
            r"uploads\bx48\report.docx",
        ],
        "grade_level": "D",
    }
    inv = {"runtime_artifacts": {"scratch_detected": True}}
    report = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert report["applied"] is True
    assert report["runtime_status"] == "BLOCKED"
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    for code in ("8/C.P5", "8/C.P6", "8/C.M3", "8/BC.D3"):
        assert by[code]["achieved"] is False, code
        assert by[code]["awardable"] is False, code
        assert by[code]["runtime_gate_block"] is True, code
    # Non-runtime criterion is untouched.
    assert by["8/B.P3"]["achieved"] is True
    # Missing mandatory Pass (C.P5/C.P6) ⇒ final band U.
    assert gr["grade_level"] == "U"


def test_gameplay_video_satisfies_gate():
    gr = {
        "criteria_results": _game_criteria(),
        "submission_paths": [r"uploads\bx\MemoryGame\MemoryGame.yyp"],
        "grade_level": "D",
    }
    inv = {
        "runtime_artifacts": {"gamemaker_detected": True},
        "gameplay_video_detected": True,
    }
    report = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert report["runtime_status"] == "PASS"
    assert report["applied"] is False  # nothing demoted
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    assert by["8/C.P5"]["achieved"] is True
    assert by["8/C.P6"]["achieved"] is True


def test_l5_human_playtest_satisfies_gate():
    gr = {
        "criteria_results": _game_criteria(),
        "submission_paths": [r"uploads\bx\game\Scrath file.sb3"],
    }
    inv = {
        "runtime_artifacts": {"scratch_detected": True},
        "l5_human_playtest": {"verified": True, "status": "complete_visual"},
    }
    report = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert report["runtime_status"] == "PASS"
    by = {r["criteria_level"]: r for r in gr["criteria_results"]}
    assert by["8/C.P6"]["achieved"] is True


def test_gate_is_idempotent():
    gr = {
        "criteria_results": _game_criteria(),
        "submission_paths": [r"uploads\bx\game\Scrath file.sb3"],
    }
    inv = {"runtime_artifacts": {"scratch_detected": True}}
    first = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert first["applied"] is True
    # Second run: already blocked → no new changes recorded.
    second = apply_runtime_evidence_gate(gr, artifact_inventory=inv)
    assert second["applied"] is False
    assert second["runtime_status"] == "BLOCKED"


def test_blocked_criterion_cannot_be_repromoted_by_finalizer():
    """Once runtime_gate_block is set, the finalizer promotion guard must hold."""
    from app.criteria_result_finalizer import _pearson_pro_blocks_promotion

    row = {"criteria_level": "8/C.P5", "runtime_gate_block": True, "achieved": False}
    # Even in non-PRO mode, the gate hold blocks any re-promotion.
    assert _pearson_pro_blocks_promotion({}, "P5", row) is True


def test_is_game_submission_detects_engines():
    assert is_game_submission({"runtime_artifacts": {"scratch_detected": True}}) is True
    assert is_game_submission({}, submission_paths=["a/MemoryGame.yyp"]) is True
    assert is_game_submission({}, submission_paths=["report.docx", "x.pptx"]) is False
