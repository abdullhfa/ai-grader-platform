"""
Shared PRO evidence signals (Arabic + English) for path and text matching.

Coverage v2.5: academic synonym layer + Arabic normalization — no AI.
Keeps B.P4 (design peer review) separate from C.P6 (final game testing docs).
"""
from __future__ import annotations

import re
from typing import Iterable, Pattern

from app.arabic_text_normalize import normalize_arabic_text


def _ar_pat(pattern: str) -> Pattern[str]:
    """Compile regex after the same Arabic normalization applied to student text."""
    return re.compile(normalize_arabic_text(pattern), re.IGNORECASE)

TEST_PLAN_TEXT_RE = re.compile(
    r"(?:"
    r"test\s*plan|test\s*cases?|bug\s*log|user\s*test(?:ing)?|play\s*test|playtest"
    r"|خطة\s*اختبار|تقرير\s*اختبار|نتائج\s*اختبار|سجل\s*أخطاء|سجل\s*الأخطاء"
    r"|اختبار\s*المستخدم|تجربة\s*المستخدم|اختبار\s*اللعبة"
    r"|functional\s*test|testing\s*phase|جدول\s*اختبار"
    r")",
    re.IGNORECASE,
)

DESIGN_PEER_TEXT_RE = re.compile(
    r"(?:"
    r"peer\s*review|design\s*review|feedback\s*on\s*design"
    r"|مراجعة\s*التصميم|مراجعين|مراجع|ملاحظات\s*المراجع"
    r"|gdd\s*v\s*2|نسخة\s*محسنة|تحسين\s*التصميم|وثيقة\s*تصميم"
    r"|استبيان.*تصميم|تصميم.*استبيان|مراجعة\s*الوثيق"
    r")",
    re.IGNORECASE,
)

_GENERIC_SURVEY_RE = re.compile(
    r"(?:questionnaire|survey|استبيان|استطلاع|ملاحظات\s*مستلمة)",
    re.IGNORECASE,
)

_FINAL_GAME_TEST_RE = re.compile(
    r"(?:"
    r"test\s*plan|bug\s*log|خطة\s*اختبار|سجل\s*أخطاء"
    r"|اختبار\s*(?:اللعبة|النهائ|وظائف)|user\s*testing|playtest"
    r")",
    re.IGNORECASE,
)

_TEST_PLAN_PATH_RE = re.compile(
    r"(?:"
    r"test[\s_-]*plan|test[\s_-]*cases|test[\s_-]*report|جدول[\s_-]*اختبار"
    r"|خطة[\s_-]*اختبار|خطة[\s_-]*فحص|حالات[\s_-]*اختبار|functional[\s_-]*test"
    r")",
    re.IGNORECASE,
)

_TESTING_DOC_PATH_RE = re.compile(
    r"(?:"
    r"test[\s_-]*plan|bug[\s_-]*log|test[\s_-]*report|user[\s_-]*test|playtest"
    r"|خطة[\s_-]*اختبار|خطة[\s_-]*فحص|سجل[\s_-]*أخطاء|سجل[\s_-]*مشاكل"
    r"|نتائج[\s_-]*اختبار|اختبار[\s_-]*مستخدم"
    r")",
    re.IGNORECASE,
)

_BUG_LOG_PATH_RE = re.compile(
    r"(?:bug[\s_-]*log|defect[\s_-]*log|سجل[\s_-]*أخطاء|سجل[\s_-]*مشاكل|اعطال)",
    re.IGNORECASE,
)

_USER_TEST_PATH_RE = re.compile(
    r"(?:user[\s_-]*test|playtest|اختبار[\s_-]*مستخدم|تجربه[\s_-]*مستخدم)",
    re.IGNORECASE,
)

_PEER_DESIGN_DOC_PATH_RE = re.compile(
    r"(?:"
    r"peer[\s_-]*review|design[\s_-]*review|gdd|game[\s_-]*design"
    r"|مراجعة[\s_-]*التصميم|تصميم[\s_-]*اللعبة|feedback"
    r")",
    re.IGNORECASE,
)

# Coverage v2.5 — academic synonym layer (normalized before match).
COVERAGE_TEST_PLAN_RE = _ar_pat(
    r"(?:"
    r"test\s*plan|test\s*cases?|testing\s*phase|functional\s*test(?:ing)?(?:\s+plan)?"
    r"|خطة\s*(?:اختبار|فحص)|جدول\s*اختبار|جدول\s*الاختبارات"
    r"|حالات\s*الاختبار|سيناريوهات\s*الاختبار|اختبارات\s*الوظائف"
    r"|منهجية\s*التحقق|تقرير\s*اختبار"
    r")"
)

COVERAGE_BUG_LOG_RE = _ar_pat(
    r"(?:"
    r"bug\s*log|defect\s*log"
    r"|سجل\s*(?:ال)?(?:اخطاء|أخطاء|مشاكل|اعطال)"
    r"|قائمة\s*الاعطال|المشكلات?\s*المكتشفة|المشاكل\s*المكتشفة"
    r"|الأخطاء\s*المكتشفة|تسجيل\s*المشاكل"
    r")"
)

USER_TESTING_EVIDENCE_RE = _ar_pat(
    r"(?:"
    r"user\s*test(?:ing)?|play\s*test|playtest|usability\s*test"
    r"|اختبار\s*(?:المستخدم|الاصدقاء|الأصدقاء|اللعبة)"
    r"|تجربة\s*(?:المستخدم|اللعبة)"
    r"|ملاحظات\s*(?:المختبرين|اللاعبين)"
    r"|آراء\s*المستخدمين|تقييم\s*اللاعبين"
    r"|feedback\s*from\s*(?:users|testers|players)"
    r"|نتائج\s*اختبار\s*(?:المستخدم|اللعبة|الوظائف)"
    r"|استطلاع\s*رضا\s*بعد"
    r")"
)

IMPROVEMENT_FROM_TEST_RE = re.compile(
    r"(?:"
    r"بناءً\s+على.*اختبار|after\s+testing|تحسين.*بعد.*اختبار"
    r"|based\s+on.*(?:test|feedback)|نتائج\s*الاختبار.*تحسين"
    r")",
    re.IGNORECASE,
)

STRENGTHS_WEAKNESSES_RE = re.compile(
    r"(?:نقاط\s*القوة|نقاط\s*ضعف|strengths|weaknesses|نقاط\s*تحتاج)",
    re.IGNORECASE,
)

COMPARISON_EVAL_RE = re.compile(
    r"(?:مقارنة|comparison|بديل|alternatives?|unity.*godot|godot.*unity)",
    re.IGNORECASE,
)

CRITICAL_EVAL_RE = re.compile(
    r"(?:تقييم\s*نقدي|critical\s*evaluation|تحليل\s*شامل|evaluate\s+the\s+process)",
    re.IGNORECASE,
)

PROJECT_LOG_RE = re.compile(
    r"(?:سجل\s*يوميات|project\s*log(?:book)?|development\s*diary|المحتوى\s*المنجز)",
    re.IGNORECASE,
)

DESIGN_DECISION_RE = re.compile(
    r"(?:قرار\s*تصميم|design\s*decision|سبب\s*اختيار|سبب\s*عدم\s*اختيار)",
    re.IGNORECASE,
)

REFLECTION_RE = re.compile(
    r"(?:انعكاس|reflection|تعلمت|تحديات|challenges\s+faced|ما\s+تعلمته)",
    re.IGNORECASE,
)

_NEGATED_EVIDENCE_RE = _ar_pat(
    r"(?:"
    r"بدون|لا\s+يوجد|لم\s+يقدم|غير\s+موجود|without|no\s+|not\s+present|missing"
    r")[\s\S]{0,40}(?:"
    r"test\s*plan|bug\s*log|خطة\s*اختبار|سجل\s*اخطاء|user\s*test"
    r")"
)


def _not_negated_match(text: str, pattern: Pattern[str]) -> bool:
    raw = text or ""
    normalized = normalize_arabic_text(raw)
    m = pattern.search(normalized)
    if not m:
        return False
    window_start = max(0, m.start() - 50)
    window = normalized[window_start : m.end()]
    return _NEGATED_EVIDENCE_RE.search(window) is None


def _path_match(pattern: Pattern[str], path: str) -> bool:
    return bool(pattern.search(normalize_arabic_text(path or "")))


def text_has_test_plan_evidence(text: str) -> bool:
    return bool(TEST_PLAN_TEXT_RE.search(text or ""))


def text_has_coverage_test_plan(text: str) -> bool:
    return _not_negated_match(text or "", COVERAGE_TEST_PLAN_RE)


def text_has_coverage_bug_log(text: str) -> bool:
    return _not_negated_match(text or "", COVERAGE_BUG_LOG_RE)


def text_has_user_testing_evidence(text: str) -> bool:
    return _not_negated_match(text or "", USER_TESTING_EVIDENCE_RE)


def text_has_improvement_from_testing(text: str) -> bool:
    return bool(IMPROVEMENT_FROM_TEST_RE.search(normalize_arabic_text(text or "")))


def text_has_critical_evaluation(text: str) -> bool:
    t = normalize_arabic_text(text or "")
    return bool(CRITICAL_EVAL_RE.search(t)) and bool(STRENGTHS_WEAKNESSES_RE.search(t))


def text_has_comparison_evaluation(text: str) -> bool:
    return bool(COMPARISON_EVAL_RE.search(normalize_arabic_text(text or "")))


def text_has_project_log(text: str) -> bool:
    t = normalize_arabic_text(text or "")
    return bool(PROJECT_LOG_RE.search(t)) and len(t) > 200


def text_has_design_decisions(text: str) -> bool:
    return bool(DESIGN_DECISION_RE.search(normalize_arabic_text(text or "")))


def text_has_reflection(text: str) -> bool:
    return bool(REFLECTION_RE.search(normalize_arabic_text(text or "")))


def text_has_design_peer_evidence(text: str, *, min_len: int = 250) -> bool:
    t = text or ""
    if len(t) < min_len:
        return False
    nt = normalize_arabic_text(t)
    if DESIGN_PEER_TEXT_RE.search(nt):
        return True
    if not _GENERIC_SURVEY_RE.search(nt):
        return False
    has_design = bool(re.search(r"gdd|تصميم|design|مراجع", nt, re.IGNORECASE))
    final_test_only = bool(_FINAL_GAME_TEST_RE.search(nt)) and not bool(
        re.search(r"مراجعة\s*التصميم|design\s*review|gdd\s*v", nt, re.IGNORECASE)
    )
    return has_design and not final_test_only


def path_looks_like_test_plan_doc(path: str) -> bool:
    return _path_match(_TEST_PLAN_PATH_RE, path)


def path_looks_like_testing_doc(path: str) -> bool:
    return _path_match(_TESTING_DOC_PATH_RE, path)


def path_looks_like_bug_log_doc(path: str) -> bool:
    return _path_match(_BUG_LOG_PATH_RE, path)


def path_looks_like_user_test_doc(path: str) -> bool:
    return _path_match(_USER_TEST_PATH_RE, path)


def path_looks_like_peer_design_doc(path: str) -> bool:
    return bool(_PEER_DESIGN_DOC_PATH_RE.search(path or ""))


def classify_named_docs(paths: Iterable[str]) -> dict[str, bool]:
    doc_paths = list(paths or [])
    return {
        "has_test_plan_doc": any(path_looks_like_test_plan_doc(p) for p in doc_paths),
        "has_testing_doc": any(path_looks_like_testing_doc(p) for p in doc_paths),
        "has_bug_log_doc": any(path_looks_like_bug_log_doc(p) for p in doc_paths),
        "has_user_test_doc": any(path_looks_like_user_test_doc(p) for p in doc_paths),
        "has_peer_design_doc": any(path_looks_like_peer_design_doc(p) for p in doc_paths),
    }
