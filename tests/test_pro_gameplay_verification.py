"""Spec §6.1 — 10 required unit tests + submission 50 integration scenario."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.gameplay_verifier import (
    CaptureFailureError,
    EvidencePackage,
    EvidenceQualityError,
    PlaytestOrchestrator,
    RequirementResult,
    RequirementVerifier,
    assess_automated_l4_gate,
    calculate_l4_level,
    run_automated_gameplay_verification,
)
from app.requirement_extractor import DEFAULT_GODOT_EXE_PLAN, InputAction, RequirementPlan, RequirementTest
from app.requirement_extractor import RequirementExtractor
from app.runtime_evidence_gate import BTECCriterionMapper, apply_runtime_evidence_gate


def _shot(label: str, scope: str = "game_window") -> dict:
    return {
        "status": "captured",
        "path": f"/tmp/{label}.png",
        "label": label,
        "capture_scope": scope,
        "game_window_detected": scope == "game_window",
    }


# §6.1 — INVARIANT #1
def test_movement_requires_gameplay_entered():
    package = EvidencePackage(gameplay_entered=False)
    package.results = [
        RequirementResult(req_id="player_movement", verified=True, confidence=0.9),
    ]
    mv = package.to_movement_verification_dict()
    assert mv["player_movement_verified"] is False
    assert mv["l4_level"] == "L3"


# §6.1 — INVARIANT #4
def test_desktop_fallback_rejected_in_pro():
    orch = PlaytestOrchestrator(pro_mode=True)
    capture = MagicMock(return_value=_shot("bad", scope="desktop_fallback"))
    plan = RequirementPlan(
        requirements=[
            RequirementTest(
                req_id="player_movement",
                input_sequence=[InputAction("key_hold", "d", duration=0.1)],
                verification_method="pixel_shift_horizontal",
                success_threshold=0.03,
            )
        ]
    )
    with pytest.raises(CaptureFailureError):
        orch.run(
            artifact_path=Path("game.exe"),
            process_pid=1,
            capture_screenshot=capture,
            plan=plan,
            elapsed_seconds=0.0,
            gameplay_entered=True,
        )


# §6.1 — INVARIANT #3
def test_jump_not_proxy_from_movement(monkeypatch):
    verifier = RequirementVerifier()
    before = _shot("b")
    after = _shot("a")
    monkeypatch.setattr(verifier, "_horizontal_centroid_shift", lambda b, a: 0.5)
    monkeypatch.setattr(verifier, "_vertical_centroid_shift", lambda b, a: 0.01)
    ok_h, _, _ = verifier.verify(
        "pixel_shift_horizontal", before, after, threshold=0.03, gameplay_entered=True
    )
    ok_v, _, _ = verifier.verify(
        "pixel_shift_vertical", before, after, threshold=0.02, gameplay_entered=True
    )
    assert ok_h is True
    assert ok_v is False


# §6.1 — Gate policy automatic C.P5
def test_gate_cp5_opens_on_l4_partial():
    gv = {
        "l4_level": "L4_partial",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 1,
        "gameplay_window_screenshots": 2,
    }
    gate = assess_automated_l4_gate(gv, functional_smoke_pass=True)
    assert gate["criterion_pass"]["P5"] is True


# §6.1 — C.P6 test doc entries (PRO vs STANDARD)
def test_gate_cp6_opens_on_l4_partial_with_single_test_entry_in_pro():
    gv = {
        "l4_level": "L4_partial",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 2,
        "gameplay_window_screenshots": 2,
    }
    gate = assess_automated_l4_gate(
        gv,
        test_doc_entries=1,
        functional_smoke_pass=True,
        grading_mode="pro",
    )
    assert gate["criterion_pass"]["P6"] is True


def test_gate_cp6_requires_two_test_entries_in_standard():
    gv = {
        "l4_level": "L4_partial",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 2,
        "gameplay_window_screenshots": 2,
    }
    one_entry = assess_automated_l4_gate(
        gv,
        test_doc_entries=1,
        functional_smoke_pass=True,
        grading_mode="standard",
    )
    two_entries = assess_automated_l4_gate(
        gv,
        test_doc_entries=2,
        functional_smoke_pass=True,
        grading_mode="standard",
    )
    assert one_entry["criterion_pass"]["P6"] is False
    assert two_entries["criterion_pass"]["P6"] is True


# §6.1 — M3 teacher confirmation
def test_gate_cm3_requires_teacher_confirmation():
    gv = {
        "l4_level": "L4_full",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 3,
        "gameplay_window_screenshots": 4,
    }
    auto = assess_automated_l4_gate(gv, test_doc_entries=2, functional_smoke_pass=True)
    confirmed = assess_automated_l4_gate(
        gv,
        test_doc_entries=2,
        functional_smoke_pass=True,
        teacher_confirmed={"M3": True},
    )
    assert auto["criterion_pass"]["M3"] is False
    assert confirmed["criterion_pass"]["M3"] is True


# §6.1 — D3 teacher confirmation
def test_gate_cd3_requires_teacher_confirmation():
    gv = {
        "l4_level": "L4_full",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 3,
        "gameplay_window_screenshots": 4,
    }
    auto = assess_automated_l4_gate(gv, test_doc_entries=2, functional_smoke_pass=True)
    confirmed = assess_automated_l4_gate(
        gv,
        test_doc_entries=2,
        functional_smoke_pass=True,
        teacher_confirmed={"D3": True},
    )
    assert auto["criterion_pass"]["D3"] is False
    assert confirmed["criterion_pass"]["D3"] is True


# §6.1 — L4 level calculation
@pytest.mark.parametrize(
    "entered,mechanics,expected",
    [
        (False, 0, "L3"),
        (False, 2, "L3"),
        (True, 0, "L3"),
        (True, 1, "L4_partial"),
        (True, 2, "L4_partial"),
        (True, 3, "L4_full"),
    ],
)
def test_l4_level_calculation_all_cases(entered, mechanics, expected):
    assert calculate_l4_level(
        gameplay_entered=entered,
        mechanics_verified_count=mechanics,
    ) == expected


# §6.1 — default Godot plan
def test_requirement_extractor_default_plan():
    plan = RequirementExtractor().default_plan(submission_id="50", engine="godot")
    ids = plan.requirement_ids()
    assert "player_movement" in ids
    assert "player_jump" in ids
    assert plan.engine == "godot"


# §6.1 — screenshot metadata tags
def test_evidence_package_screenshot_tags(monkeypatch):
    monkeypatch.setattr("app.gameplay_verifier._key_hold", lambda *a, **k: True)
    calls: list[dict] = []

    def capture(*args, **kwargs):
        shot = _shot(str(kwargs.get("label") or "cap"))
        calls.append(kwargs)
        return shot

    verifier = RequirementVerifier()
    monkeypatch.setattr(
        verifier,
        "verify",
        lambda method, before, after, threshold, gameplay_entered=True: (True, 1.0, "ok"),
    )
    plan = RequirementPlan(
        requirements=[
            RequirementTest(
                req_id="player_movement",
                input_sequence=[InputAction("key_hold", "d", duration=0.1)],
                verification_method="pixel_shift_horizontal",
                success_threshold=0.03,
            )
        ]
    )
    orch = PlaytestOrchestrator(pro_mode=True, verifier=verifier)
    package = orch.run(
        artifact_path=Path("game.exe"),
        process_pid=None,
        capture_screenshot=capture,
        plan=plan,
        elapsed_seconds=0.0,
        gameplay_entered=True,
    )
    assert package.screenshots
    tagged = package.screenshots[0]
    assert tagged.get("requirement_id") == "player_movement"
    assert tagged.get("phase") in ("before", "after")
    assert tagged.get("capture_scope") == "game_window"


# §6.2 — Submission 50 integration scenario (synthetic evidence chain)
def test_submission_50_integration_scenario():
    """Ahmad Bakr — L4_partial opens C.P5/C.P6; M3/D3 need teacher."""
    gv = {
        "l4_level": "L4_partial",
        "gameplay_entered": True,
        "player_movement_verified": True,
        "mechanics_verified_count": 1,
        "gameplay_window_screenshots": 2,
        "evidence_package": {
            "results": [
                {"req_id": "player_movement", "verified": True, "btec_criteria": ["C.P5"]},
            ]
        },
    }
    gate = BTECCriterionMapper(grading_mode="pro").evaluate(
        gv,
        test_doc_entries=1,
        functional_smoke_pass=True,
    )
    assert gate["criterion_pass"]["P5"] is True
    assert gate["criterion_pass"]["P6"] is True
    assert gate["criterion_pass"]["M3"] is False
    assert gate["criterion_pass"]["D3"] is False

    criteria = [
        {"criteria_level": "8/C.P5", "achieved": True, "score": 75},
        {"criteria_level": "8/C.P6", "achieved": True, "score": 70},
        {"criteria_level": "8/C.M3", "achieved": True, "score": 65},
        {"criteria_level": "8/BC.D3", "achieved": False, "score": 40},
    ]
    gr = {
        "grade_level": "P",
        "grading_mode": "deep",
        "criteria_results": criteria,
        "artifact_inventory": {
            "runtime_validation": {"functional_smoke": {"functional_smoke_pass": True}},
            "intake_relative_paths": ["test plan.docx", "survey results.pdf"],
            "gameplay_verification": gv,
            "runtime_observation_report": {"status": "completed", "gameplay_verification": gv},
            "executable_artifacts": {"files": ["P_03.exe"]},
            "runtime_artifacts": {"godot_export_detected": True},
        },
        "submission_paths": ["uploads/student/P_03.exe"],
    }
    report = apply_runtime_evidence_gate(gr)
    cp5 = next(r for r in gr["criteria_results"] if "P5" in r["criteria_level"])
    cp6 = next(r for r in gr["criteria_results"] if "P6" in r["criteria_level"])
    assert not cp5.get("runtime_gate_block")
    assert not cp6.get("runtime_gate_block")
    assert report.get("automated_l4_gate", {}).get("criterion_pass", {}).get("P5") is True
