"""Visual evidence registry — Found / Submitted / Analyzed / Used separation."""
from __future__ import annotations

from typing import Any, Dict

from app.academic_explainability import build_missing_evidence_diagnostics
from app.evidence_registry import attach_evidence_registry_and_metrics, build_grade_display_metrics
from app.visual_evidence_registry import (
    attach_visual_evidence_to_grading_result,
    build_criterion_authority_record,
    build_criterion_visual_evidence,
    build_visual_evidence_summary,
    criterion_evidence_class,
    sync_visual_evidence_to_inventory,
)


def test_summary_not_analysed_when_found_but_zero_analyzed():
    s = build_visual_evidence_summary(
        images_found=34,
        images_analyzed=0,
        vision_attempted=False,
        vision_completed=False,
    )
    assert s["images_found"] == 34
    assert s["images_analyzed"] == 0
    assert s["images_submitted"] == 0
    assert s["images_used_in_decision"] == 0
    assert s["vision_status"] == "not_analysed"


def test_summary_failed_when_attempted_but_empty_response():
    s = build_visual_evidence_summary(
        images_found=20,
        images_submitted=15,
        images_analyzed=0,
        vision_attempted=True,
        vision_completed=False,
        vision_error="empty_vision_response",
    )
    assert s["vision_status"] == "failed"
    assert s["vision_error"] == "empty_vision_response"
    assert s["images_used_in_decision"] == 0
    assert "فشل Vision" in s["vision_status_ar"]


def test_summary_used_when_vision_completed():
    s = build_visual_evidence_summary(
        images_found=20,
        images_submitted=10,
        images_analyzed=10,
        vision_attempted=True,
        vision_completed=True,
    )
    assert s["images_used_in_decision"] == 10
    assert s["vision_status"] == "partially_analysed"


def test_text_sufficient_criterion_uses_text_basis_only():
    summary = build_visual_evidence_summary(images_found=34, images_analyzed=0)
    vis = build_criterion_visual_evidence(
        criteria_level="8/B.P4",
        criteria_description="peer review",
        summary=summary,
        achieved=True,
        verdict_status="pass",
        authority="DETERMINISTIC",
        evidence_registry={"evidence_found": [{"rule_key": "استبيان", "snippet": "x"}]},
    )
    assert vis["evidence_class"] == "text_sufficient"
    assert vis["decision_basis"] == "text"
    assert vis["result"] == "PASS"
    assert vis["visual_authority_required"] is False
    assert vis["authority"]["text_authority_available"] is True
    assert vis["images_used_in_decision"] == 0


def test_visual_dependent_inconclusive_no_runtime_when_vision_ok():
    summary = build_visual_evidence_summary(
        images_found=10,
        images_submitted=10,
        images_analyzed=10,
        vision_attempted=True,
        vision_completed=True,
    )
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P5",
        criteria_description="gameplay",
        summary=summary,
        achieved=False,
        verdict_status="inconclusive",
        authority="DETERMINISTIC_INCONCLUSIVE",
    )
    assert vis["decision_basis"] == "inconclusive_no_runtime"
    assert vis["authority"]["visual_authority_available"] is True


def test_visual_dependent_inconclusive_without_vision():
    summary = build_visual_evidence_summary(
        images_found=10,
        images_submitted=10,
        images_analyzed=0,
        vision_attempted=True,
        vision_completed=False,
        vision_error="empty_vision_response",
    )
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P5",
        criteria_description="gameplay",
        summary=summary,
        achieved=False,
        verdict_status="inconclusive",
        authority="DETERMINISTIC_INCONCLUSIVE",
    )
    assert vis["evidence_class"] == "visual_dependent"
    assert vis["decision_basis"] == "inconclusive_no_visual_authority"
    assert vis["result"] == "INCONCLUSIVE"
    assert vis["visual_authority_required"] is True
    assert vis["visual_authority_available"] is False
    assert vis["authority"]["runtime_authority_required"] is True
    assert vis["authority"]["authority_sufficient"] is False


def test_c_p6_inconclusive_grader_hold_when_testing_ok():
    summary = build_visual_evidence_summary(
        images_found=5,
        images_submitted=5,
        images_analyzed=5,
        vision_attempted=True,
        vision_completed=True,
    )
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P6",
        criteria_description="test game",
        summary=summary,
        achieved=False,
        verdict_status="inconclusive",
        authority="DETERMINISTIC_INCONCLUSIVE",
        evidence_registry={
            "evidence_found": [
                {
                    "rule_key": "مرحلة_الاختبار",
                    "snippet": "مرحلة الاختبار تم خلالها اختبار حركة اللاعب",
                }
            ]
        },
    )
    assert vis["decision_basis"] == "inconclusive_no_structured_test_plan"
    assert vis["authority"]["testing_authority_available"] is True
    assert vis["authority"]["authority_sufficient"] is True


def test_c_p6_inconclusive_no_testing_basis():
    summary = build_visual_evidence_summary(
        images_found=5,
        images_submitted=5,
        images_analyzed=5,
        vision_attempted=True,
        vision_completed=True,
    )
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P6",
        criteria_description="test game",
        summary=summary,
        achieved=False,
        verdict_status="inconclusive",
        authority="DETERMINISTIC_INCONCLUSIVE",
    )
    assert vis["decision_basis"] == "inconclusive_no_testing"
    assert vis["authority"]["visual_authority_available"] is True


def test_c_p6_testing_authority_from_structured_text_evidence():
    auth = build_criterion_authority_record(
        criteria_level="8/C.P6",
        criteria_description="test game",
        summary=build_visual_evidence_summary(images_found=5, images_analyzed=5, vision_completed=True),
        achieved=False,
        verdict_status="inconclusive",
        evidence_registry={
            "evidence_found": [
                {
                    "rule_key": "مرحلة_الاختبار",
                    "snippet": "مرحلة الاختبار تم خلالها اختبار حركة اللاعب",
                }
            ]
        },
    )
    assert auth["testing_authority_required"] is True
    assert auth["testing_authority_available"] is True


def test_c_p6_no_testing_authority_from_bare_test_word():
    auth = build_criterion_authority_record(
        criteria_level="8/C.P6",
        criteria_description="test game",
        summary=build_visual_evidence_summary(),
        achieved=False,
        verdict_status="inconclusive",
        evidence_registry={
            "evidence_found": [{"rule_key": "generic", "snippet": "كلمة اختبار عامة فقط"}]
        },
    )
    assert auth["testing_authority_available"] is False


def test_missing_evidence_diagnostics_follows_p6_testing_authority():
    """Authority C.P6 testing ✓ must not emit missing-testing diagnostics."""
    inv = {
        "grading_mode_note_ar": "وضع BASIC — تقييم سريع",
        "runtime_observation_report": {"status": "skipped_fast_mode"},
        "documentation": {"status": "analyzed", "files": [{"name": "g.docx", "ext": ".docx"}]},
        "source_code": {"status": "detected", "files": [{"name": "main.gd", "ext": ".gd"}]},
        "has_source_code_artifacts": True,
        "embedded_screenshots": {"count": 5},
        "vision_analysis_used": True,
        "executable_artifacts": {"files": []},
        "testing_evidence": {"status": "not_detected"},
        "criterion_authority": [
            {
                "criterion": "8/C.P6",
                "testing_authority_available": True,
                "authority_sufficient": True,
                "decision_basis": "inconclusive_no_structured_test_plan",
            }
        ],
    }
    diag = build_missing_evidence_diagnostics(inv, grading_mode="fast")
    rows = {r["requirement_ar"]: r for r in diag["rows"]}
    testing_row = rows["أدلة الاختبار (خطط/سجلات)"]
    assert testing_row["present"] is True
    assert testing_row["blocks_achievement_ar"] == ""
    assert "لا testing evidence" not in testing_row["blocks_achievement_ar"]
    assert testing_row["status_ar"] == "تحديث الى خطة برو"


def test_c_p6_inconclusive_formal_docs_when_testing_artifact_present():
    summary = build_visual_evidence_summary(
        images_found=5,
        images_submitted=5,
        images_analyzed=5,
        vision_attempted=True,
        vision_completed=True,
    )
    vis = build_criterion_visual_evidence(
        criteria_level="8/C.P6",
        criteria_description="test game",
        summary=summary,
        achieved=False,
        verdict_status="inconclusive",
        authority="GRADER_HOLD",
        evidence_registry={
            "evidence_found": [
                {
                    "rule_key": "test_plan",
                    "snippet": "Test plan for player movement",
                }
            ]
        },
        artifact_inventory={"testing_evidence": {"status": "documented"}},
    )
    assert vis["decision_basis"] == "inconclusive_formal_testing_docs_required"
    assert vis["authority"]["testing_authority_available"] is True


def test_attach_enriches_grading_result_and_metrics():
    grading: Dict[str, Any] = {
        "grade_level": "U",
        "criteria_results": [
            {
                "criteria_level": "8/B.P4",
                "achieved": True,
                "evidence_registry": {
                    "criterion": "8/B.P4",
                    "rule_id": "x",
                    "result": "pass",
                },
            },
        ],
    }
    attach_visual_evidence_to_grading_result(
        grading,
        images_found=34,
        images_submitted=0,
        images_analyzed=0,
        vision_attempted=False,
        vision_completed=False,
        criteria_descriptions={"8/B.P4": "peer review"},
    )
    attach_evidence_registry_and_metrics(grading, grading_mode="fast")
    assert grading["visual_evidence_summary"]["images_found"] == 34
    assert len(grading.get("criterion_authority") or []) == 1
    reg = grading["criteria_results"][0]["evidence_registry"]
    assert reg["visual_evidence"]["images_used_in_decision"] == 0
    gdm = grading["grade_display_metrics"]
    assert gdm["visual_evidence"]["images_analyzed"] == 0


def test_sync_inventory_failed_when_attempted_not_completed():
    inv = {"embedded_screenshots": {"count": 20, "status": "analyzed"}}
    summary = build_visual_evidence_summary(
        images_found=20,
        images_submitted=15,
        images_analyzed=0,
        vision_attempted=True,
        vision_completed=False,
        vision_error="empty_vision_response",
    )
    sync_visual_evidence_to_inventory(inv, summary)
    assert inv["vision_analysis_used"] is False
    assert inv["embedded_screenshots"]["vision_analyzed_count"] == 0
    assert inv["embedded_screenshots"]["vision_submitted_count"] == 15
    assert inv["embedded_screenshots"]["status"] == "failed"


def test_sync_inventory_not_analysed_when_never_attempted():
    inv = {"embedded_screenshots": {"count": 34, "status": "analyzed"}}
    summary = build_visual_evidence_summary(images_found=34, images_analyzed=0)
    sync_visual_evidence_to_inventory(inv, summary)
    assert inv["vision_analysis_used"] is False
    assert inv["embedded_screenshots"]["vision_analyzed_count"] == 0
    assert inv["embedded_screenshots"]["status"] == "not_analysed"


def test_criterion_evidence_class_hybrid_for_bp3():
    assert criterion_evidence_class("8/B.P3", "design document gdd") == "hybrid"
