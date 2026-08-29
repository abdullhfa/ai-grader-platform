from app.design_evidence_assessor import try_evaluate_design_criterion
from app.rubric.deterministic_engine import evaluate_criterion_deterministic


def _inventory() -> dict:
    return {
        "documentation": {"status": "analyzed", "files": [{"name": "design.docx"}]},
        "embedded_screenshots": {"count": 4},
        "visual_verification": {"screenshots_analyzed": 4},
    }


def test_bp3_does_not_pass_without_required_test_plan():
    row = try_evaluate_design_criterion(
        criteria_level="8/B.P3",
        corpus=(
            "وثيقة تصميم اللعبة ومتطلبات المستخدم. mechanics levels controls "
            "واجهة وشاشة وتصميم بصري. تبرير قرار التصميم."
        ),
        artifact_inventory=_inventory(),
        execution_mode="PRO",
    )
    assert row is not None
    assert row["deterministic_achieved"] is False


def test_bp4_does_not_pass_from_screenshots_alone():
    row = try_evaluate_design_criterion(
        criteria_level="8/B.P4",
        corpus="وثيقة تصميم اللعبة واجهة شاشة وصور للتصميم " * 30,
        artifact_inventory=_inventory(),
        execution_mode="PRO",
    )
    assert row is not None
    assert row["deterministic_achieved"] is False


def test_cp7_runtime_and_document_do_not_replace_client_review():
    row = evaluate_criterion_deterministic(
        criteria_level="8/C.P7",
        criteria_description="مراجعة مدى تلبية لعبة الحاسوب لمتطلبات العميل.",
        student_text="لعبة GameMaker مع صور وعرض للعبة. " * 30,
        runtime_validation={"smoke_success": True},
        execution_mode="PRO",
    )
    assert row["deterministic_achieved"] is False
    assert row["rule_id"] == "client_requirements_review_v1"


def test_generated_vision_summary_is_not_student_academic_evidence():
    text = (
        "وثيقة تصميم أولية بلا مراجعة أو خطة اختبار.\n"
        "=== تحليل الصور/الفيديو (Vision) ===\n"
        "مراجعة مدى تلبية اللعبة لمتطلبات العميل، تعليقات مستخدمين، "
        "وخطة اختبار ونسخة محسنة بناء على الملاحظات."
    )
    row = evaluate_criterion_deterministic(
        criteria_level="8/C.P7",
        criteria_description="مراجعة مدى تلبية لعبة الحاسوب لمتطلبات العميل.",
        student_text=text,
        runtime_validation={"smoke_success": True},
        execution_mode="PRO",
    )
    assert row["deterministic_achieved"] is False


def test_cm3_requires_improvement_tied_to_user_testing():
    row = evaluate_criterion_deterministic(
        criteria_level="8/C.M3",
        criteria_description="تحسين لعبة حاسوب لتلبية متطلبات العميل.",
        student_text="تحليل وقرارات تصميم كثيرة دون اختبار مستخدم أو تحسين موثق. " * 30,
        execution_mode="PRO",
    )
    assert row["deterministic_achieved"] is False


def test_complete_design_review_and_client_review_can_still_pass():
    bp3 = try_evaluate_design_criterion(
        criteria_level="8/B.P3",
        corpus=(
            "وثيقة تصميم اللعبة ومتطلبات المستخدم mechanics levels controls. "
            "واجهة شاشة وتصميم بصري. خطة اختبار وحالات الاختبار للوظائف. " * 12
        ),
        artifact_inventory=_inventory(),
        execution_mode="PRO",
    )
    assert bp3 is not None and bp3["deterministic_achieved"] is True

    bp4 = try_evaluate_design_criterion(
        criteria_level="8/B.P4",
        corpus=(
            "راجع شخصان من الزملاء تصميم اللعبة وقدما ملاحظات وتعليقات. "
            "بناء على ملاحظات المراجعين حسنت واجهة التصميم وأنشأت نسخة محسنة. " * 12
        ),
        artifact_inventory=_inventory(),
        execution_mode="PRO",
    )
    assert bp4 is not None and bp4["deterministic_achieved"] is True

    cp7 = evaluate_criterion_deterministic(
        criteria_level="8/C.P7",
        criteria_description="مراجعة مدى تلبية لعبة الحاسوب لمتطلبات العميل.",
        student_text=(
            "تقييم مدى تلبية اللعبة لمتطلبات العميل ومتطلبات المستخدم، مع تحليل "
            "الفعالية والاستنتاجات ونقاط القوة والضعف في النسخة النهائية. " * 12
        ),
        execution_mode="PRO",
    )
    assert cp7["deterministic_achieved"] is True

    cm3 = evaluate_criterion_deterministic(
        criteria_level="8/C.M3",
        criteria_description="تحسين لعبة حاسوب لتلبية متطلبات العميل.",
        student_text=(
            "بعد اختبار المستخدم وملاحظات اللاعبين تم تحسين اللعبة بناء على نتائج "
            "الاختبار، مع توثيق النسخة قبل وبعد التحسين. " * 12
        ),
        execution_mode="PRO",
    )
    assert cm3["deterministic_achieved"] is True
