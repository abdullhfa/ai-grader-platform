"""Fair BTEC award for Aim B/C + V1/V2 GameMaker evidence (Jana-like PRO)."""
from __future__ import annotations

JANA_LIKE = (
    "وثيقة تصميم لعبة CheeseChase. الجمهور المستهدف من 8 إلى 12 سنة. "
    "الغرض من اللعبة بناء على متطلبات العميل هو تجربة واضحة وممتعة للأطفال. "
    "خيارات التطوير: قمت باختيار التحكم بالفأرة بناء على استبيان الأطفال. "
    "تبرير قرار التصميم للواجهة والنقاط والأرواح بعد ملاحظات ليلى وسارة. "
    "الجدول الزمني وخطة العمل قسّما المشروع إلى مراحل متسلسلة لإدارة الوقت وتحقيق الأهداف. "
    "أظهرت المسؤولية الفردية وتوليت بنفسي عقد اجتماع رسمي وجها لوجه والتواصل مع العميل. "
    "محور التحسين بعد الاختبار: سرعة القطة وأقنعة التصادم ومزامنة الجبن. "
    "أجريت تقييما وتحليلا شاملا للنسخة الأولية مقارنة بالنسخة المطورة وبحل بديل، "
    "واستنتجت فعالية التغييرات مقابل متطلبات العميل ونقاط القوة والضعف. "
    "قدمت مقترحات وتوصيات واتخذت قرارا مبررا بناء على نتائج المستخدمين. "
    "خطة اختبار ونتائج اختبار اللعبة للنسخة النهائية مع جدول الحالات. "
    + ("تفاصيل التصميم " * 80)
)


def test_deterministic_p4_and_m2_pass_on_design_survey_corpus():
    from app.rubric.deterministic_engine import evaluate_criterion_deterministic

    p4 = evaluate_criterion_deterministic(
        criteria_level="8/B.P4",
        criteria_description="Review the designs with others using a questionnaire or survey",
        student_text=JANA_LIKE,
        execution_mode="PRO",
        artifact_inventory={"documentation": {"status": "present", "files": ["Aim B.docx"]}},
    )
    assert p4["deterministic_achieved"] is True

    m2 = evaluate_criterion_deterministic(
        criteria_level="8/B.M2",
        criteria_description="Justify design decisions",
        student_text=JANA_LIKE,
        execution_mode="PRO",
    )
    assert m2["deterministic_achieved"] is True
    assert m2["rule_id"] == "bm2_design_justification"


def test_deterministic_d2_and_d3_pass_only_on_complete_documentary_corpus():
    from app.rubric.deterministic_engine import evaluate_criterion_deterministic

    d2 = evaluate_criterion_deterministic(
        criteria_level="8/BC.D2",
        criteria_description="Evaluate the design and improved game against client requirements",
        student_text=JANA_LIKE,
        execution_mode="PRO",
    )
    d3 = evaluate_criterion_deterministic(
        criteria_level="8/BC.D3",
        criteria_description="Individual responsibility, creativity and effective self-management",
        student_text=JANA_LIKE,
        execution_mode="PRO",
    )

    assert d2["deterministic_achieved"] is True
    assert d2["rule_id"] == "bc_d2_evaluation"
    assert d3["deterministic_achieved"] is True
    assert d3["rule_id"] == "bc_d3_self_management"


def test_finalizer_restores_academic_m2_d2_and_clears_stale_ai_denials():
    from app.criteria_result_finalizer import finalize_grading_criteria_results

    achieved = lambda level: {
        "criteria_level": level,
        "achieved": True,
        "score": 85,
        "feedback": "تم تحقيق المعيار.",
        "missing_points": [],
    }
    denied = lambda level, rule: {
        "criteria_level": level,
        "achieved": False,
        "score": 35,
        "feedback": "لم يتم تحقيق المعيار ويحتاج إلى مراجعة بشرية.",
        "missing_points": ["مراجعة بشرية"],
        "decision_matrix": [{"met": False, "evidence": "", "reasoning": "لم يتم تحقيق المعيار."}],
        "deterministic_rubric": {
            "deterministic_achieved": True,
            "deterministic_score": 95,
            "verdict_status": "pass",
            "authority": "ACADEMIC_TEXT_RULE_V1",
            "rule_id": rule,
        },
    }
    result = {
        "pearson_btec_pro": True,
        "grade_level": "P",
        "student_text": JANA_LIKE,
        "criteria_results": [
            achieved("8/B.P3"),
            achieved("8/B.P4"),
            achieved("8/C.P5"),
            achieved("8/C.P6"),
            achieved("8/C.P7"),
            denied("8/B.M2", "bm2_design_justification"),
            achieved("8/C.M3"),
            denied("8/BC.D2", "bc_d2_evaluation"),
            achieved("8/BC.D3"),
        ],
    }

    finalize_grading_criteria_results(result, artifact_inventory={})
    by_level = {row["criteria_level"]: row for row in result["criteria_results"]}

    assert result["grade_level"] == "D"
    for level in ("8/B.M2", "8/BC.D2"):
        assert by_level[level]["achieved"] is True
        assert by_level[level]["missing_points"] == []
        assert "لم يتم تحقيق" not in by_level[level]["feedback"]


def test_gamemaker_d3_never_opens_from_documents_plus_l4_alone():
    from app.runtime_evidence_gate import BTECCriterionMapper

    def row(level: str, rule: str) -> dict:
        return {
            "criteria_level": level,
            "achieved": False,
            "score": 35,
            "feedback": "لم يتم تحقيق المعيار تلقائيا.",
            "covered_points": [],
            "missing_points": ["مراجعة بشرية"],
            "decision_matrix": [{"met": False, "evidence": "", "reasoning": ""}],
            "deterministic_rubric": {
                "deterministic_achieved": True,
                "verdict_status": "pass",
                "authority": "ACADEMIC_TEXT_RULE_V1",
                "rule_id": rule,
            },
        }

    result = BTECCriterionMapper().evaluate(
        {
            "gameplay_entered": True,
            "l4_level": "L4_full",
            "player_movement_verified": True,
            "mechanics_verified_count": 3,
            "gameplay_window_screenshots": 12,
        },
        test_doc_entries=1,
        functional_smoke_pass=True,
        criteria_results=[
            row("8/C.M3", "merit_analysis"),
            row("8/BC.D3", "bc_d3_self_management"),
        ],
        engine_id="gamemaker",
        student_text=JANA_LIKE,
    )

    assert result["criterion_pass"]["M3"] is False
    assert result["criterion_pass"]["D3"] is False
    d3 = next(d for d in result["decisions"] if d["criterion"] == "D3")
    assert d3["automatic"] is True
    assert "teacher_confirmation_required" not in d3
    assert d3["reason"] == "prerequisite_m3_not_met"
    # Advisory only: a strong documentary corpus is reported but cannot open
    # Distinction by itself — D3 needs a passed M3 (which needs a V1→V2 code diff).
    assert d3["ai_academic_verified"] is True


def test_gamemaker_m3_does_not_open_on_l4_partial_with_improvement_docs():
    from app.runtime_evidence_gate import BTECCriterionMapper

    m3_row = {
        "criteria_level": "C.M3",
        "achieved": False,
        "score": 35,
        "covered_points": ["محور التحسين بعد الاختبار"],
        "missing_points": [],
        "decision_matrix": [
            {
                "requirement": "C.M3",
                "met": False,
                "evidence": "جدول تحسينات ونتائج اختبار النموذج الأولي",
                "reasoning": "عرض تقني منظم وفعال يشرح الاختبار والتحسين بناء على الملاحظات.",
            }
        ],
        "deterministic_rubric": {
            "deterministic_achieved": True,
            "verdict_status": "pass",
            "authority": "DETERMINISTIC",
            "evidence_registry": {"visual_evidence": {"authority": {"authority_sufficient": True}}},
        },
    }
    d3_row = {
        "criteria_level": "C.D3",
        "achieved": False,
        "score": 20,
        "covered_points": [],
        "missing_points": ["critical evaluation"],
        "decision_matrix": [{"requirement": "C.D3", "met": False, "evidence": "", "reasoning": ""}],
        "deterministic_rubric": {"deterministic_achieved": False, "verdict_status": "fail"},
    }
    result = BTECCriterionMapper().evaluate(
        {
            "gameplay_entered": False,
            "l4_level": "L4_partial",
            "player_movement_verified": False,
            "mechanics_verified_count": 0,
            "gameplay_window_screenshots": 6,
        },
        test_doc_entries=1,
        functional_smoke_pass=True,
        criteria_results=[m3_row, d3_row],
        engine_id="gamemaker",
        student_text=JANA_LIKE,
    )
    assert result["criterion_pass"]["M3"] is False
    assert result["criterion_pass"]["D3"] is False
