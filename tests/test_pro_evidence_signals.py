"""Tests for PRO evidence path/text signals."""

from app.pro_evidence_signals import (
    path_looks_like_peer_design_doc,
    path_looks_like_testing_doc,
    text_has_design_peer_evidence,
    text_has_test_plan_evidence,
)


def test_test_plan_arabic_and_english():
    assert text_has_test_plan_evidence("وثيقة خطة اختبار مع نتائج")
    assert text_has_test_plan_evidence("Bug Log and Test Plan attached")
    assert not text_has_test_plan_evidence("استبيان تقييم التصميم الأولي فقط")


def test_design_peer_not_final_game_test():
    long_design = (
        "مراجعة التصميم مع الآخرين. استبيان على GDD الأولي. "
        "نسخة محسنة من وثيقة تصميم اللعبة. " + ("تفاصيل " * 40)
    )
    assert text_has_design_peer_evidence(long_design)

    final_test_only = (
        "استمارات تقييم وملاحظات مستلمة من اختبار اللعبة النهائية. "
        "خطة اختبار و Bug Log للنسخة النهائية. " + ("x" * 200)
    )
    assert not text_has_design_peer_evidence(final_test_only)


def test_path_name_detection():
    assert path_looks_like_testing_doc(r"uploads\student\Bug_Log.docx")
    assert path_looks_like_testing_doc("خطة_اختبار.pdf")
    assert path_looks_like_peer_design_doc("GDD_v2_peer_review.docx")
    assert path_looks_like_peer_design_doc("مراجعة_التصميم.docx")
