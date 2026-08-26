import app.gameplay_verifier as gameplay_verifier
import app.runtime_evidence_gate as runtime_gate
from app.runtime_evidence_gate import BTECCriterionMapper


def _verification(confidence_rows):
    return {
        "gameplay_entered": True,
        "l4_level": "L4_full",
        "mechanics_verified_count": 4,
        "player_movement_verified": True,
        "gameplay_window_screenshots": 12,
        "requirement_checklist": {
            "requirements": [
                {"id": "player_movement", "applicability": "required"},
                {"id": "jump", "applicability": "not_mentioned"},
                {"id": "score_system", "applicability": "required"},
                {"id": "win_condition", "applicability": "required"},
                {"id": "lose_condition", "applicability": "required"},
                {"id": "level_design", "applicability": "required"},
            ]
        },
        "runtime_evidence_package": {"requirement_confidence": confidence_rows},
    }


def _row(requirement, verified, source="runtime_l4"):
    return {
        "requirement": requirement,
        "verified": verified,
        "confidence_source": source,
    }


def test_required_feature_failure_blocks_p5_and_p6_despite_l4_full():
    verification = _verification(
        [
            _row("player_movement", True),
            _row("score_system", False),
            _row("win_condition", False),
            _row("lose_condition", False),
        ]
    )

    result = BTECCriterionMapper(grading_mode="PRO").evaluate(
        verification,
        test_doc_entries=1,
        engine_id="gamemaker",
    )

    assert result["criterion_pass"]["P5"] is False
    assert result["criterion_pass"]["P6"] is False
    required = result["required_feature_verification"]
    assert required["missing"] == ["score_system", "win_condition", "lose_condition"]
    p5 = next(row for row in result["decisions"] if row["criterion"] == "P5")
    assert p5["reason"] == "required_gameplay_features_unverified"


def test_source_runtime_corroboration_fairly_satisfies_unreached_features():
    verification = _verification(
        [
            _row("player_movement", True),
            _row("score_system", True, "cross_modal_l4"),
            _row("win_condition", True, "cross_modal_l4"),
            _row("lose_condition", True, "cross_modal_l4"),
        ]
    )

    result = BTECCriterionMapper(grading_mode="PRO").evaluate(
        verification,
        test_doc_entries=1,
        engine_id="gamemaker",
    )

    assert result["criterion_pass"]["P5"] is True
    assert result["criterion_pass"]["P6"] is True
    assert result["required_feature_verification"]["all_verified"] is True


def test_documentation_and_non_required_features_do_not_block_runtime_gate():
    verification = _verification(
        [
            _row("player_movement", True),
            _row("score_system", True),
            _row("win_condition", True),
            _row("lose_condition", True),
        ]
    )

    result = BTECCriterionMapper(grading_mode="PRO").evaluate(
        verification,
        test_doc_entries=1,
    )

    required = result["required_feature_verification"]
    assert "jump" not in required["required"]
    assert "level_design" not in required["required"]
    assert result["criterion_pass"]["P5"] is True


def test_legacy_snapshot_without_requirement_rows_keeps_legacy_gate_behavior():
    result = BTECCriterionMapper(grading_mode="PRO").evaluate(
        {
            "gameplay_entered": True,
            "l4_level": "L4_full",
            "mechanics_verified_count": 4,
            "player_movement_verified": True,
        },
        test_doc_entries=1,
    )

    assert result["required_feature_verification"]["available"] is False
    assert result["criterion_pass"]["P5"] is True
    assert result["criterion_pass"]["P6"] is True


def test_terminal_gate_demotes_previously_awarded_rows_when_required_features_fail(
    monkeypatch,
):
    confidence_rows = [
        _row("player_movement", True),
        _row("score_system", False),
        _row("win_condition", False),
        _row("lose_condition", False),
    ]
    verification = _verification(confidence_rows)
    grading_result = {
        "grading_mode": "PRO",
        "criteria_results": [
            {"criteria_level": "8/C.P5", "achieved": True, "awardable": True, "score": 75},
            {"criteria_level": "8/C.P6", "achieved": True, "awardable": True, "score": 75},
            {"criteria_level": "8/C.M3", "achieved": True, "awardable": True, "score": 85},
        ],
        "gameplay_verification": verification,
        "requirement_checklist": verification["requirement_checklist"],
        "runtime_evidence_package": verification["runtime_evidence_package"],
        "artifact_inventory": {
            "gameplay_verification": verification,
            "assets_detected": {"testing_documentation": True},
        },
    }
    monkeypatch.setattr(runtime_gate, "is_game_submission", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        runtime_gate,
        "evaluate_runtime_evidence",
        lambda *_args, **_kwargs: {
            "status": "PASS",
            "satisfied": True,
            "engine_id": "gamemaker",
            "accepted_evidence": "runtime",
        },
    )
    monkeypatch.setattr(gameplay_verifier, "sync_authoritative_gv", lambda *_args, **_kwargs: None)

    report = runtime_gate.apply_runtime_evidence_gate(grading_result)

    assert report["automated_l4_gate"]["criterion_pass"]["P5"] is False
    assert report["automated_l4_gate"]["criterion_pass"]["P6"] is False
    for row in grading_result["criteria_results"]:
        assert row["achieved"] is False
        assert row["awardable"] is False
        assert row["runtime_gate_block"] is True
    assert grading_result["grade_level"] == "U"
