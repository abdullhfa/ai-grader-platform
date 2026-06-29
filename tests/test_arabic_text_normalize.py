from app.arabic_text_normalize import normalize_arabic_text
from app.pro_evidence_signals import text_has_coverage_bug_log


def test_normalize_unifies_alef_and_hamza():
    assert normalize_arabic_text("الأخطاء") == normalize_arabic_text("الاخطاء")


def test_bug_log_without_hamza_matches():
    assert text_has_coverage_bug_log("سجل الاخطاء البرمجية")
