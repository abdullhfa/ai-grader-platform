from app.pro_engine_gameplay_governance import apply_pro_engine_gameplay_governance
from app.runtime_evidence_gate import _promote_l4_gate_row


def test_d2_and_d3_are_not_gameplay_gated():
    rows = [
        {"criteria_level": "8/C.P6", "achieved": True, "score": 100},
        {"criteria_level": "8/C.M3", "achieved": True, "score": 100},
        {"criteria_level": "8/BC.D2", "achieved": True, "score": 100},
        {"criteria_level": "8/BC.D3", "achieved": True, "score": 100},
    ]
    apply_pro_engine_gameplay_governance(rows, artifact_inventory={})
    by_short = {row["criteria_level"].split(".")[-1]: row for row in rows}
    assert by_short["P6"]["achieved"] is False
    assert by_short["M3"]["achieved"] is False
    assert by_short["D2"]["achieved"] is True
    assert by_short["D3"]["achieved"] is True


def test_runtime_promotion_keeps_nested_deterministic_audit_consistent():
    row = {
        "criteria_level": "8/C.P5",
        "achieved": True,
        "score": 75,
        "achievement_authority": "DETERMINISTIC",
        "deterministic_rubric": {
            "deterministic_achieved": False,
            "deterministic_score": 0,
            "verdict_status": "fail",
            "reason": "no_code_evidence",
            "authority": "DETERMINISTIC",
            "evidence_registry": {"result": "fail", "runtime": "none"},
        },
    }

    _promote_l4_gate_row(row)

    assert row["deterministic_rubric"]["deterministic_achieved"] is True
    assert row["deterministic_rubric"]["reason"] == "runtime_l4_verified_override"
    assert row["achievement_authority"] == "RUNTIME_VALIDATION"
    assert row["pre_runtime_deterministic_rubric"]["reason"] == "no_code_evidence"
