"""Decision Provenance v1 — rule bundle stamping."""
from __future__ import annotations

from typing import Any

from app.evidence_registry import attach_evidence_registry_and_metrics
from app.explainability_migration import compute_academic_decision_digest
from app.rule_bundle import (
    AUTHORITY_VERSION,
    ENGINE_VERSION,
    RULE_VERSION,
    build_decision_provenance,
    compute_bundle_hash,
    copy_provenance,
    format_rule_bundle_label,
)
from app.visual_evidence_registry import (
    attach_visual_evidence_to_grading_result,
    build_criterion_visual_evidence,
    build_visual_evidence_summary,
)


def test_build_decision_provenance_basic():
    prov = build_decision_provenance("fast")
    assert prov["rule_version"] == RULE_VERSION
    assert prov["authority_version"] == AUTHORITY_VERSION
    assert prov["engine_version"] == ENGINE_VERSION
    assert prov["execution_mode"] == "BASIC"
    assert len(prov["bundle_hash"]) == 64


def test_bundle_hash_changes_with_execution_mode():
    basic = build_decision_provenance("fast")
    pro = build_decision_provenance("deep")
    assert basic["bundle_hash"] != pro["bundle_hash"]
    assert basic["execution_mode"] == "BASIC"
    assert pro["execution_mode"] == "PRO"


def test_bundle_hash_includes_all_five_fields():
    h1 = compute_bundle_hash(
        rule_version=RULE_VERSION,
        authority_version=AUTHORITY_VERSION,
        engine_version=ENGINE_VERSION,
        governance_freeze="GOVERNANCE_FREEZE_v1",
        execution_mode="BASIC",
    )
    h2 = compute_bundle_hash(
        rule_version=RULE_VERSION,
        authority_version=AUTHORITY_VERSION,
        engine_version=ENGINE_VERSION,
        governance_freeze="GOVERNANCE_FREEZE_v1",
        execution_mode="PRO",
    )
    assert h1 != h2


def test_same_provenance_copied_to_authority_and_registry():
    grading: dict[str, Any] = {
        "grading_mode": "fast",
        "criteria_results": [
            {
                "criteria_level": "8/C.P6",
                "achieved": False,
                "verdict_status": "inconclusive",
                "authority": "DETERMINISTIC_INCONCLUSIVE",
                "evidence_registry": {
                    "criterion": "8/C.P6",
                    "rule_id": "test_doc_runtime_inconclusive",
                    "result": "inconclusive",
                    "evidence_found": [{"rule_key": "مرحلة_الاختبار", "snippet": "اختبار حركة اللاعب"}],
                    "evidence_missing": [],
                },
            }
        ],
    }
    attach_visual_evidence_to_grading_result(
        grading,
        images_found=5,
        images_analyzed=5,
        vision_completed=True,
        criteria_descriptions={"8/C.P6": "testing"},
    )
    top_raw = grading["decision_provenance"]
    assert isinstance(top_raw, dict)
    top: dict[str, Any] = top_raw
    auth_rows = grading["criterion_authority"]
    assert isinstance(auth_rows, list) and auth_rows
    auth_row = auth_rows[0]
    assert isinstance(auth_row, dict)
    auth_prov_raw = auth_row["decision_provenance"]
    assert isinstance(auth_prov_raw, dict)
    auth: dict[str, Any] = auth_prov_raw
    assert top["bundle_hash"] == auth["bundle_hash"]
    assert top is not auth
    assert auth["execution_mode"] == "BASIC"


def test_attach_evidence_registry_stamps_provenance():
    grading: dict[str, Any] = {
        "grading_mode": "fast",
        "criteria_results": [
            {
                "criteria_level": "8/B.P4",
                "achieved": True,
                "evidence_registry": {
                    "criterion": "8/B.P4",
                    "rule_id": "x",
                    "result": "pass",
                    "evidence_found": [],
                    "evidence_missing": [],
                },
            }
        ],
    }
    out: dict[str, Any] = attach_evidence_registry_and_metrics(grading, grading_mode="fast")
    prov_raw = out["decision_provenance"]
    assert isinstance(prov_raw, dict)
    prov: dict[str, Any] = prov_raw
    ev_reg = out["evidence_registry"]
    assert isinstance(ev_reg, dict)
    ev_prov = ev_reg["decision_provenance"]
    assert isinstance(ev_prov, dict)
    gdm = out["grade_display_metrics"]
    assert isinstance(gdm, dict)
    assert prov["bundle_hash"]
    assert ev_prov["bundle_hash"] == prov["bundle_hash"]
    assert gdm["rule_bundle_label"] == format_rule_bundle_label(prov)


def test_academic_decision_digest_includes_provenance():
    prov = build_decision_provenance("fast")
    d1 = compute_academic_decision_digest(
        grade_level="U",
        percentage=62.0,
        criteria_results=[{"criteria_level": "8/C.P6", "achieved": False}],
        decision_provenance=prov,
    )
    d2 = compute_academic_decision_digest(
        grade_level="U",
        percentage=62.0,
        criteria_results=[{"criteria_level": "8/C.P6", "achieved": False}],
        decision_provenance=copy_provenance(prov),
    )
    pro_prov = build_decision_provenance("deep")
    d3 = compute_academic_decision_digest(
        grade_level="U",
        percentage=62.0,
        criteria_results=[{"criteria_level": "8/C.P6", "achieved": False}],
        decision_provenance=pro_prov,
    )
    assert d1 == d2
    assert d1 != d3


def test_criterion_visual_evidence_carries_provenance():
    prov = build_decision_provenance("fast")
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P6",
        criteria_description="testing",
        summary=build_visual_evidence_summary(images_found=5, images_analyzed=5, vision_completed=True),
        achieved=False,
        verdict_status="inconclusive",
        authority="DETERMINISTIC_INCONCLUSIVE",
        evidence_registry={
            "evidence_found": [{"rule_key": "مرحلة_الاختبار", "snippet": "اختبار حركة اللاعب"}]
        },
        decision_provenance=prov,
    )
    authority = vis["authority"]
    assert isinstance(authority, dict)
    auth_prov = authority["decision_provenance"]
    assert isinstance(auth_prov, dict)
    assert auth_prov["bundle_hash"] == prov["bundle_hash"]
