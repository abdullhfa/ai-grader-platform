"""Tests for BTEC criteria governance post-processing."""
from __future__ import annotations

from typing import Any

from app.btec_grade_resolution import determine_grade_level
from app.btec_criteria_governance import (
    apply_btec_awardability,
    apply_btec_criteria_governance,
)


def _base_criteria() -> list[dict[str, Any]]:
    return [
        {"criteria_level": "8/B.P3", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/B.P4", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/C.P5", "achieved": False, "score": 20, "feedback": "no runtime"},
        {"criteria_level": "8/C.P6", "achieved": False, "score": 10, "feedback": "no test"},
        {"criteria_level": "8/C.P7", "achieved": True, "score": 80, "feedback": "ok"},
        {"criteria_level": "8/B.M2", "achieved": True, "score": 90, "feedback": "ok"},
        {"criteria_level": "8/C.M3", "achieved": True, "score": 90, "feedback": "ok"},
        {"criteria_level": "8/BC.D2", "achieved": True, "score": 90, "feedback": "ok"},
        {"criteria_level": "8/BC.D3", "achieved": True, "score": 90, "feedback": "ok"},
    ]


def _by_level(criteria: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {str(r["criteria_level"]): r for r in criteria}


def test_m2_stays_achieved_but_not_awardable_when_pass_incomplete():
    crit = _base_criteria()
    assert determine_grade_level(crit) == "U"
    award = apply_btec_awardability(crit)
    by = _by_level(crit)
    assert by["8/B.M2"]["achieved"] is True
    assert by["8/B.M2"]["awardable"] is False
    assert by["8/B.M2"]["award_block_reason"] == "missing_pass_criteria"
    assert by["8/BC.D2"]["achieved"] is True
    assert by["8/BC.D2"]["awardable"] is False
    assert award["institutional_grade"] == "U"
    assert "8/C.P5" in award["missing_pass_criteria"]


def test_governance_keeps_achievement_separate_from_award():
    gr: dict[str, Any] = {"grade_level": "D", "percentage": 72, "criteria_results": _base_criteria()}
    report = apply_btec_criteria_governance(gr)
    by = _by_level(gr["criteria_results"])
    assert by["8/B.M2"]["achieved"] is True
    assert by["8/B.M2"]["awardable"] is False
    assert gr["grade_level"] == "U"
    inst_award = gr.get("btec_institutional_award")
    assert isinstance(inst_award, dict)
    assert inst_award.get("reason_code") == "missing_pass_criteria"
    report_award = report.get("awardability")
    assert isinstance(report_award, dict)
    assert report_award.get("achieved_not_awardable")


def test_all_pass_m2_awardable():
    crit = [
        {"criteria_level": "8/B.P3", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/B.P4", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/C.P5", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/B.M2", "achieved": True, "score": 90, "feedback": "ok"},
    ]
    apply_btec_awardability(crit)
    by = _by_level(crit)
    assert determine_grade_level(crit) == "M"
    assert by["8/B.M2"]["awardable"] is True


def test_partial_pass_no_m_d_is_u():
    crit = [
        {"criteria_level": "8/B.P3", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/B.P4", "achieved": True, "score": 85, "feedback": "ok"},
        {"criteria_level": "8/C.P5", "achieved": False, "score": 20, "feedback": "no"},
        {"criteria_level": "8/B.M2", "achieved": False, "score": 10, "feedback": "no"},
    ]
    assert determine_grade_level(crit) == "U"


def test_feedback_contradiction_flips_achieved():
    crit = _base_criteria()
    crit[4] = {
        "criteria_level": "8/C.P7",
        "achieved": True,
        "score": 80,
        "feedback": "لم يقدم الطالب أي مراجعة للعبة المكتملة.",
    }
    gr = {
        "grade_level": "U",
        "percentage": 40,
        "criteria_results": crit,
        # Informative (present-but-empty) inventory: we positively know there are no
        # game artifacts, so demotion is valid (vs a blind/missing inventory).
        "artifact_inventory": {"source_code": {"files": []}, "executable_artifacts": {"files": []}},
    }
    report = apply_btec_criteria_governance(gr)
    assert report["applied"] is True
    by = _by_level(gr["criteria_results"])
    assert by["8/C.P7"]["achieved"] is False
    assert by["8/C.P7"]["awardable"] is False


def test_doc_only_demotes_execution_criteria():
    crit = _base_criteria()
    for row in crit:
        if row["criteria_level"] in ("8/C.P5", "8/C.P6"):
            row["achieved"] = True
            row["score"] = 70
    gr = {
        "grade_level": "D",
        "percentage": 80,
        "criteria_results": crit,
        "artifact_inventory": {"source_code": {"files": []}, "executable_artifacts": {"files": []}},
    }
    report = apply_btec_criteria_governance(gr)
    assert report["applied"] is True
    by = _by_level(gr["criteria_results"])
    assert by["8/C.P5"]["achieved"] is False
    assert by["8/C.M3"]["achieved"] is False
    assert by["8/B.M2"]["achieved"] is True
    assert by["8/B.M2"]["awardable"] is False
    assert gr["grade_level"] == "U"


def test_strip_btec_governance_feedback_removes_prefix():
    from app.btec_criteria_governance import strip_btec_governance_feedback

    raw = (
        "⚠️ [حوكمة BTEC] الملاحظة تنفي وجود الدليل المطلوب — لا يمكن اعتبار المعيار متحققاً.\n"
        "قدم الطالب مراجعة للمتطلبات."
    )
    assert strip_btec_governance_feedback(raw) == "قدم الطالب مراجعة للمتطلبات."


def test_strip_btec_governance_feedback_removes_repeated_ai_disclaimers():
    from app.btec_criteria_governance import strip_btec_governance_feedback

    raw = (
        "⚠️ [حوكمة BTEC] لم يتحقق المعيار مؤسسياً.\n\n"
        "[تحليل الذكاء الاصطناعي — غير معتمد بعد الحوكمة]\n"
        "[تحليل الذكاء الاصطناعي — غير معتمد بعد الحوكمة]\n"
        "لم يتم تحقيق المعيار. لا توجد خطة اختبار."
    )
    assert strip_btec_governance_feedback(raw) == "لم يتم تحقيق المعيار. لا توجد خطة اختبار."


def test_strip_btec_governance_feedback_removes_inline_ai_disclaimers():
    from app.btec_criteria_governance import strip_btec_governance_feedback

    raw = (
        "[تحليل الذكاء الاصطناعي — غير معتمد بعد الحوكمة] "
        "[تحليل الذكاء الاصطناعي — غير معتمد بعد الحوكمة] "
        "لم يتم تحقيق المعيار."
    )
    assert strip_btec_governance_feedback(raw) == "لم يتم تحقيق المعيار."


def test_not_achieved_denial_feedback_not_rewrapped_on_repeat():
    from app.btec_criteria_governance import enforce_not_achieved_feedback_consistency

    crit = [
        {
            "criteria_level": "8/C.P6",
            "achieved": False,
            "score": 45,
            "feedback": (
                "⚠️ [حوكمة BTEC] لم يتحقق المعيار مؤسسياً.\n\n"
                "[تحليل الذكاء الاصطناعي — غير معتمد بعد الحوكمة]\n"
                "لم يتم تحقيق المعيار. يتطلب Test Plan و Bug Log."
            ),
        },
    ]
    enforce_not_achieved_feedback_consistency(crit)
    enforce_not_achieved_feedback_consistency(crit)
    fb = crit[0]["feedback"]
    assert fb.count("[تحليل الذكاء الاصطناعي") == 0
    assert "لم يتم تحقيق المعيار" in fb


def test_not_achieved_positive_feedback_gets_governance_prefix():
    crit = [
        {
            "criteria_level": "8/C.P5",
            "achieved": False,
            "score": 0,
            "feedback": "حقق الطالب المعيار بامتياز. يوجد final.apk و game.exe.",
            "deterministic_rubric": {
                "reason": "missing_evidence:source_code",
                "deterministic_achieved": False,
            },
            "decision_matrix": [{"requirement": "8/C.P5", "met": True, "reasoning": "حقق الطالب المعيار بامتياز."}],
        },
    ]
    gr = {
        "grade_level": "U",
        "percentage": 10,
        "criteria_results": crit,
        "evidence_completeness_gate": {
            "assets_detected": {"executable": True, "source_code": False},
        },
    }
    apply_btec_criteria_governance(gr)
    fb = gr["criteria_results"][0]["feedback"]
    assert "لم يتحقق المعيار مؤسسياً" in fb
    assert "حقق الطالب" not in fb
    assert "[تحليل الذكاء الاصطناعي" not in fb
    assert "⚠️ [حوكمة BTEC]" not in fb
    assert gr["criteria_results"][0]["decision_matrix"][0]["met"] is False


def test_achieved_not_awardable_replaces_ai_praise():
    crit = _base_criteria()
    apply_btec_awardability(crit)
    by = _by_level(crit)
    assert by["8/B.M2"]["awardable"] is False
    from app.btec_criteria_governance import enforce_achieved_not_awardable_feedback

    by["8/B.M2"]["feedback"] = "تم تحقيق المعيار بشكل ممتاز."
    changes = enforce_achieved_not_awardable_feedback(crit)
    assert changes
    assert "جزئياً" in by["8/B.M2"]["feedback"]
    assert "ممتاز" not in by["8/B.M2"]["feedback"]
    assert "C.P5" in by["8/B.M2"]["feedback"] or "Prerequisite" in by["8/B.M2"]["feedback"]


def test_align_overall_feedback_removes_distinction_praise_for_u():
    from app.btec_criteria_governance import align_overall_feedback_with_institutional_grade

    gr = {
        "grade_level": "U",
        "overall_feedback": "أداء ممتاز ومتميز. قدرتك على التقييم النقدي دليل على Distinction.",
        "runtime_evidence_gate": {"runtime_status": "BLOCKED"},
    }
    changes = align_overall_feedback_with_institutional_grade(gr)
    assert changes
    fb = gr["overall_feedback"]
    assert "C.P5" in fb or "Gameplay" in fb
    assert "أداء ممتاز" not in fb
    assert "Distinction" not in fb


def test_execution_demotion_skipped_when_gate_sees_exe(tmp_path):
    exe = tmp_path / "game.exe"
    exe.write_bytes(b"x" * 10)
    crit = [
        {
            "criteria_level": "8/C.P5",
            "achieved": True,
            "score": 70,
            "feedback": "ok",
        },
    ]
    gr = {
        "grade_level": "P",
        "percentage": 70,
        "criteria_results": crit,
        "artifact_inventory": {"executable_artifacts": {"files": []}},
        "evidence_completeness_gate": {
            "assets_detected": {"executable": True, "source_code": True},
        },
    }
    apply_btec_criteria_governance(gr)
    row = gr["criteria_results"][0]
    assert row["achieved"] is True
    gov_ar = str(row.get("governance_adjustment_ar") or "")
    assert "لا توجد ملفات مشروع" not in gov_ar


def test_execution_demotion_skipped_for_scratch_in_paths():
    """A .sb3 in submission_paths must count as a game artifact even on a slim
    inventory (no runtime_artifacts/source flags), preventing a false
    "لا توجد ملفات مشروع" demotion of C.P5/C.P6."""
    crit = [
        {"criteria_level": "8/C.P5", "achieved": True, "score": 70, "feedback": "ok"},
        {"criteria_level": "8/C.P6", "achieved": True, "score": 70, "feedback": "ok"},
    ]
    gr = {
        "grade_level": "P",
        "percentage": 70,
        "criteria_results": crit,
        "artifact_inventory": {},  # slim — no source/runtime flags
        "submission_paths": [
            r"uploads\students\bx48\العاب\Scrath file.sb3",
            r"uploads\students\bx48\report.docx",
        ],
    }
    apply_btec_criteria_governance(gr)
    by = _by_level(gr["criteria_results"])
    assert by["8/C.P5"]["achieved"] is True
    for row in gr["criteria_results"]:
        assert "لا توجد ملفات مشروع" not in str(row.get("governance_adjustment_ar") or "")
        assert "لا توجد ملفات مشروع" not in str(row.get("feedback") or "")


def test_no_changes_when_all_consistent():
    crit = [
        {"criteria_level": "8/B.P3", "achieved": True, "score": 85, "feedback": "دليل كافٍ"},
        {"criteria_level": "8/B.P4", "achieved": False, "score": 20, "feedback": "ناقص"},
    ]
    gr = {"grade_level": "U", "percentage": 20, "criteria_results": crit}
    report = apply_btec_criteria_governance(gr)
    assert report["applied"] is False
    report_award = report.get("awardability")
    assert isinstance(report_award, dict)
    assert report_award.get("institutional_grade") == "U"
