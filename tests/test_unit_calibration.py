"""Tests for Unit 9 games calibration spec."""
from __future__ import annotations

from app.pearson_unit_spec_registry import compare_uploaded_criteria_to_official, lookup_unit_spec
from app.unit_calibration import (
    UNIT9_KEY,
    assess_moe_engine_compliance,
    assignment_brief_criteria,
    criterion_by_code,
    get_unit9_spec,
    moe_approved_engine_ids,
    runtime_gated_codes,
)


def test_unit9_spec_loads():
    spec = get_unit9_spec()
    assert spec["unit"]["moe_number"] == 9
    assert spec["unit"]["pearson_number"] == 8
    assert len(spec["criteria"]) == 9


def test_grade_folder_layout():
    from app.unit_calibration import list_grade_ids, load_grade_manifest

    assert "grade_10" in list_grade_ids()
    g10 = load_grade_manifest("grade_10")
    assert g10 is not None
    assert g10["active_units"][0]["slug"] == "games"


def test_assignment_brief_has_eight_criteria():
    brief = assignment_brief_criteria()
    codes = {r["code"] for r in brief}
    assert codes == {"B.P3", "B.P4", "B.M2", "B.D2", "C.P5", "C.P6", "C.M3", "C.D3"}


def test_runtime_gate_codes_match_platform():
    assert runtime_gated_codes() == frozenset({"P5", "P6", "M3", "D3"})
    cp5 = criterion_by_code("C.P5")
    assert cp5 is not None
    assert cp5["runtime_gate"] is True
    assert cp5["requires_runtime"] is True


def test_moe_engines_five_approved():
    approved = moe_approved_engine_ids()
    assert approved == frozenset({"godot", "unity", "unreal", "scratch", "gamemaker"})


def test_moe_compliance_scratch_sb3():
    result = assess_moe_engine_compliance(submission_paths=["student/game.sb3"])
    assert result["compliant"] is True
    assert result["engine"] == "scratch"


def test_moe_compliance_unknown_engine_warn():
    result = assess_moe_engine_compliance(engine="construct")
    assert result["compliant"] is False
    assert result["policy"] == "warn"


def test_pearson_registry_lookup():
    spec = lookup_unit_spec("unit_9_games")
    assert spec is not None
    assert spec["moe_number"] == 9
    assert len(spec["criteria"]) == 9


def test_freeze_checklist_not_ready_yet():
    from app.unit_calibration import get_freeze_checklist

    fc = get_freeze_checklist()
    assert fc["ready_to_freeze"] is False
    assert "min_three_real_submissions" in fc["blockers"] or "all_five_moe_engines_detectable" in fc["blockers"]


def test_criteria_have_evidence_ar_templates():
    from app.unit_calibration import criterion_by_code

    p5 = criterion_by_code("C.P5")
    assert p5 is not None
    assert p5.get("evidence_found_ar")
    assert p5.get("gate") == "runtime_gate_block"
    uploaded = [{"criteria_level": f"8/{c}"} for c in ("B.P3", "B.P4", "C.P5", "C.P6", "B.M2", "C.M3", "BC.D2", "BC.D3")]
    report = compare_uploaded_criteria_to_official(uploaded, unit_key=UNIT9_KEY, brief_only=True)
    assert report["status"] == "compared"
    assert report["aligned"] is True
    assert report["missing_from_upload"] == []
