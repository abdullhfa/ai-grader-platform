"""Evidence coverage score and missing evidence report."""

import json
from pathlib import Path

from app.evidence_coverage_score import (
    COVERAGE_VERSION,
    attach_evidence_coverage_package,
    build_missing_evidence_report,
    compute_evidence_coverage_by_criterion,
)
from app.pro_evidence_signals import (
    text_has_coverage_bug_log,
    text_has_coverage_test_plan,
    text_has_user_testing_evidence,
)
from app.student_evidence_text import isolate_student_submission_text


def _rich_inventory():
    return {
        "documentation": {
            "files": [
                {"path": "GDD_v1.docx", "ext": ".docx"},
                {"path": "Test_Plan.docx", "ext": ".docx"},
                {"path": "Bug_Log.docx", "ext": ".docx"},
            ],
            "file_count": 3,
        },
        "source_code": {"files": [{"path": "player.gd", "ext": ".gd"}]},
        "executable_artifacts": {"files": [{"path": "game.exe", "ext": ".exe"}]},
        "has_executable_artifacts": True,
        "has_source_code_artifacts": True,
        "runtime_observation_report": {"runtime_verified": True},
        "intake_relative_paths": ["peer_review_design.docx"],
    }


def test_coverage_v25_version():
    assert COVERAGE_VERSION == "evidence_coverage_v2.6"


def test_coverage_cp6_high_with_test_and_bug():
    inv = _rich_inventory()
    text = "خطة اختبار شاملة مع سجل أخطاء واختبار المستخدم ونتائج اختبار اللعبة."
    rows = compute_evidence_coverage_by_criterion(inv, student_text=text, submission_paths=[])
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    assert cp6["coverage_pct"] >= 90


def test_path_only_test_plan_is_ten_percent_not_thirty_five():
    inv = {"documentation": {"files": [{"path": "Test_Plan.docx"}]}}
    rows = compute_evidence_coverage_by_criterion(inv, student_text="", submission_paths=[])
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    assert cp6["coverage_pct"] == 10
    assert any("اسم ملف فقط" in x for x in cp6["evidence_found_ar"])


def test_report_final_with_strong_content_full_cp6():
    inv = {
        "documentation": {"files": [{"path": "report_final.docx"}]},
        "executable_artifacts": {"files": [{"path": "game.exe"}]},
        "has_executable_artifacts": True,
        "runtime_observation_report": {"runtime_verified": True},
    }
    text = """
    منهجية التحقق من جودة اللعبة
    قائمة الأعطال المكتشفة أثناء التشغيل
    ملاحظات اللاعبين بعد التجربة
    """
    rows = compute_evidence_coverage_by_criterion(inv, student_text=text, submission_paths=[])
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    assert cp6["coverage_pct"] >= 80


def test_arabic_synonyms_detected():
    assert text_has_coverage_test_plan("خطة فحص اللعبة")
    assert text_has_coverage_test_plan("حالات الاختبار المتوقعة")
    assert text_has_coverage_test_plan("منهجية التحقق من الوظائف")
    assert text_has_coverage_bug_log("قائمة الأعطال")
    assert text_has_coverage_bug_log("سجل الاخطاء")
    assert text_has_user_testing_evidence("ملاحظات اللاعبين")
    assert text_has_user_testing_evidence("اختبار الأصدقاء للعبة")


def test_runtime_only_cp6_is_low_not_fifty():
    inv = {
        "documentation": {"files": [{"path": "report.docx"}]},
        "executable_artifacts": {"files": [{"path": "game.exe"}]},
        "runtime_observation_report": {"runtime_verified": True},
        "has_executable_artifacts": True,
    }
    rows = compute_evidence_coverage_by_criterion(
        inv,
        student_text="لعبة منجزة جاهزة للتشغيل.",
        submission_paths=[],
    )
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    assert cp6["coverage_pct"] <= 20


def test_ai_governance_text_does_not_inflate_test_plan():
    polluted = (
        "عبارات مثل «تم التنفيذ/الاختبار/التحسين» في الوورد لا تُعد دليلاً "
        "إلا إذا وافقتها لقطات أو نتائج اختبار أو ما يظهر هنا من كود."
    )
    inv = {"documentation": {"files": []}, "executable_artifacts": {"files": []}}
    rows = compute_evidence_coverage_by_criterion(inv, student_text=polluted, submission_paths=[])
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    assert cp6["coverage_pct"] == 0


def test_word_only_text_preferred_over_polluted_bundle():
    word_only = "تصميم اللعبة GDD مع استبيان مراجعة التصميم مع الآخرين."
    polluted = (
        "FORBIDDEN: game_tested\n"
        + word_only
        + "\nنتائج اختبار مذكورة في تعليق المقيّم فقط."
    )
    isolated = isolate_student_submission_text(polluted, word_only_text=word_only)
    assert "FORBIDDEN" not in isolated
    assert "GDD" in isolated


def test_cp7_capped_when_cp6_low():
    inv = {
        "documentation": {"files": [{"path": "report.docx"}]},
        "executable_artifacts": {"files": [{"path": "game.exe"}]},
        "has_executable_artifacts": True,
    }
    text = (
        "مراجعة المتطلبات requirement review effectiveness "
        "نقاط القوة نقاط الضعف"
    )
    rows = compute_evidence_coverage_by_criterion(inv, student_text=text, submission_paths=[])
    cp6 = next(r for r in rows if r["criteria_level"].endswith("P6"))
    cp7 = next(r for r in rows if r["criteria_level"].endswith("P7"))
    assert cp6["coverage_pct"] < 40
    assert cp7["coverage_pct"] <= 40
    assert cp7.get("coverage_capped_by")


def test_m3_d2_not_inflated_by_word_count_only():
    inv = {"documentation": {"files": [{"path": "long.docx"}]}}
    text = "نص طويل " * 200
    rows = compute_evidence_coverage_by_criterion(inv, student_text=text, submission_paths=[])
    m3 = next(r for r in rows if r["criteria_level"].endswith("M3"))
    d2 = next(r for r in rows if r["criteria_level"].endswith("D2"))
    d3 = next(r for r in rows if r["criteria_level"].endswith("D3"))
    assert m3["coverage_pct"] < 50
    assert d2["coverage_pct"] < 50
    assert d3["coverage_pct"] < 70


def test_missing_evidence_report_lists_gaps():
    inv = {"documentation": {"files": []}, "executable_artifacts": {"files": []}}
    rows = compute_evidence_coverage_by_criterion(inv, student_text="نص قصير", submission_paths=[])
    report = build_missing_evidence_report(rows, grade_level="U")
    assert report["cp6_coverage_pct"] < 50
    assert report["blocks_merit_distinction"] is True
    assert report["coverage_note_ar"]
    assert any(i["symbol"] == "✗" for i in report["items"])


def test_coverage_blocks_merit_when_cp6_low():
    grading = {
        "grade_level": "M",
        "criteria_results": [
            {"criteria_level": "8/C.M3", "achieved": True, "awardable": True},
            {"criteria_level": "8/BC.D2", "achieved": True, "awardable": True},
        ],
        "artifact_inventory": {"documentation": {"files": []}},
    }
    pkg = attach_evidence_coverage_package(grading, student_text="x")
    assert grading["criteria_results"][0]["awardable"] is False
    assert pkg["changes"]


def test_ahmad_like_submission_if_debug_inventory_present():
    inv_path = Path("uploads/debug/احمد_بكر_حاتم_ابو_شعيرة_artifact_inventory.json")
    txt_path = Path("uploads/debug/احمد بكر حاتم ابو شعيرة_extracted.txt")
    if not inv_path.exists() or not txt_path.exists():
        return
    inv = json.loads(inv_path.read_text(encoding="utf-8"))
    full_text = txt_path.read_text(encoding="utf-8")
    rows = compute_evidence_coverage_by_criterion(
        inv,
        student_text=full_text,
        submission_paths=[],
    )
    by = {r["criteria_level"]: r["coverage_pct"] for r in rows}
    assert by["8/C.P6"] <= 20
    assert by["8/C.M3"] <= 40
    assert by["8/BC.D2"] <= 40
    assert by["8/BC.D3"] < 100
