"""PRO-only Pearson BTEC package — BASIC must not apply hardening."""
from __future__ import annotations

from app.pro_btec_pearson import (
    apply_pro_execution_runtime_cap,
    apply_pro_pearson_btec_package,
    apply_pro_evidence_gate_demotions,
    build_authenticity_summary,
    institutional_grade_from_awardable,
    validate_unit_award,
)


def test_runtime_validation_cap_demotes_p5_without_test_doc():
    criteria = [
        {
            "criteria_level": "8/C.P5",
            "achieved": True,
            "score": 75,
            "achievement_authority": "RUNTIME_VALIDATION",
        }
    ]
    gate = {"per_criterion": [], "assets_detected": {}}
    changes = apply_pro_execution_runtime_cap(criteria, gate_report=gate)
    assert changes
    assert criteria[0]["achieved"] is False


def test_institutional_grade_uses_awardable_not_achieved_only():
    criteria = [
        {"criteria_level": "8/B.P3", "achieved": True, "awardable": True},
        {"criteria_level": "8/B.P4", "achieved": True, "awardable": False},
        {"criteria_level": "8/B.M2", "achieved": True, "awardable": False},
        {"criteria_level": "8/BC.D2", "achieved": True, "awardable": False},
    ]
    assert institutional_grade_from_awardable(criteria) == "U"


def test_fast_mode_skips_pearson_package():
    gr = {"criteria_results": [{"criteria_level": "C.P5", "achieved": True, "score": 80}]}
    out = apply_pro_pearson_btec_package(gr, grading_mode="fast")
    assert out["applied"] is False
    assert "pearson_btec_pro" not in gr


def test_unit_award_blocks_merit_when_pass_incomplete():
    criteria = [
        {"criteria_level": "C.P1", "achieved": True, "awardable": True},
        {"criteria_level": "C.P4", "achieved": False, "awardable": False},
        {"criteria_level": "C.M2", "achieved": True, "awardable": False},
    ]
    unit = validate_unit_award(criteria)
    assert unit["pass_complete"] is False
    assert unit["merit_unit_awardable"] is False


def test_authenticity_warning_not_automatic_fail():
    auth = build_authenticity_summary({"ai_likelihood": 85})
    assert auth["automatic_fail_prohibited"] is True


def test_engine_governance_demotes_p6_without_playtest():
    from app.pro_engine_gameplay_governance import apply_pro_engine_gameplay_governance

    criteria = [
        {
            "criteria_level": "8/C.P6",
            "achieved": True,
            "score": 75,
            "achievement_authority": "RUNTIME_VALIDATION",
        }
    ]
    inv = {
        "runtime_observation_report": {
            "status": "completed",
            "runtime_verified": True,
            "game_launch_attempted": False,
            "platform_analyses": [
                {
                    "signals": {
                        "runtime_method": "godot_pck_pairing_smoke",
                        "pck_pairing": {"paired": True},
                    }
                }
            ],
        },
        "runtime_validation": {
            "functional_smoke": {"functional_smoke_pass": False},
        },
        "intake_relative_paths": ["exe/final.pck", "project.godot"],
    }
    changes, assessment = apply_pro_engine_gameplay_governance(
        criteria, inv, gameplay_checks={}
    )
    assert changes
    assert criteria[0]["achieved"] is False
    assert criteria[0].get("pro_gameplay_governance_hold")
    assert assessment["engine_id"] == "godot"


def test_engine_governance_allows_l5_human_playtest():
    from app.pro_engine_gameplay_governance import apply_pro_engine_gameplay_governance

    criteria = [{"criteria_level": "8/C.P6", "achieved": True, "score": 75}]
    inv = {
        "runtime_observation_report": {
            "human_playtest_verified": True,
            "game_launch_attempted": False,
        },
        "intake_relative_paths": ["game.exe"],
    }
    changes, assessment = apply_pro_engine_gameplay_governance(criteria, inv)
    assert not changes
    assert assessment["any_path_satisfied"]


def test_fast_mode_skips_engine_governance_via_pearson():
    gr = {
        "criteria_results": [
            {"criteria_level": "8/C.P6", "achieved": True, "score": 75},
        ],
        "evidence_completeness_gate": {"per_criterion": [], "assets_detected": {}},
    }
    out = apply_pro_pearson_btec_package(gr, grading_mode="fast")
    assert out["applied"] is False
    assert "pro_engine_playtest_assessment" not in gr
