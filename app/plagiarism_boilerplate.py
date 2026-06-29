"""
Strip shared BTEC / assignment boilerplate before plagiarism similarity scoring.

Reduces inflated scores when classmates repeat the same unit brief, criterion
headings, and cover-sheet fields — without hiding copied student-owned prose.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Iterable, List, Pattern, Tuple

# Longest phrases first — applied in strip_plagiarism_boilerplate().
_BTEC_BOILERPLATE_PHRASES: Tuple[str, ...] = (
    # Unit 8 assignment brief (Arabic)
    "وثائق التصميم والاختبار ومراجعة التعليقات لتحسين اللعبة",
    "يطلب منك إعداد التصميمات الفنية والبصرية الخاصة بلعبتك",
    "يُطلب منك إعداد التصميمات الفنية والبصرية الخاصة بلعبتك",
    "إعداد التصميمات الفنية والبصرية الخاصة بلعبتك",
    "إعداد التصميمات الفنية والبصرية للعبة",
    "إعداد التصميمات الفنية والمرئية للعبة",
    "إعداد التصميم الفني والمرئي للعبة",
    "إعداد التصميمات الفنية والمرئية",
    "إعداد التصميمات الفنية والبصرية",
    "إعداد التصميم الفني والمرئي",
    "تطوير العناصر التفاعلية للعبة",
    "تطوير العناصر التفاعلية",
    "اختبار ومراجعة اللعبة الرقمية",
    "اختبار اللعبة الرقمية",
    "اختبار ومراجعة اللعبة",
    "اختبار اللعبة",
    "تطوير اللعبة الرقمية باستخدام أدوات مناسبة",
    "تفسير القرارات التصميمية للعبة",
    "تفسير القرارات التصميمية",
    "تحسينات على اللعبة بناءً على التغذية الراجعة",
    "تحسينات بناءً على التغذية الراجعة",
    "تقييم شامل لمخرجات اللعبة مقابل أهداف التصميم الأصلية",
    "تقييم شامل لمخرجات اللعبة",
    "تحديد الفئة المستهدفة ومتطلباتها البصرية",
    "موجز المتطلبات بما في ذلك الجمهور والغرض من اللعبة",
    "موجز المتطلبات بما في ذلك الجمهوروالغرض من اللعبة",
    "الوحدة الثامنة تطوير العاب الحاسوب",
    "وحدة تطوير ألعاب الحاسوب",
    "تطوير العاب الحاسوب",
    "تطوير ألعاب الحاسوب",
    "تحليل مهمّة تصميم وتطوير لعبة حاسوب",
    "تحليل مهمة تصميم وتطوير لعبة حاسوب",
    "متطلبات الجمهور المستهدف",
    "الفئة العمرية المستهدفة",
    "الجمهور المستهدف",
    "متطلبات العميل",
    "الغرض من اللعبة",
    "ميزات اللعبة",
    "من عمر 8 إلى 12 سنة",
    "من 8 إلى 12 سنة",
    "من 8-12 سنة",
    "بين 8 و 12 سنة",
    "بين 8 و12 سنة",
    "8-12 سنة",
    "8 إلى 12",
    # Unit 8 assignment brief (English)
    "design and testing documents to improve the game",
    "prepare the visual and artistic designs for your game",
    "develop the interactive elements for your game",
    "test the digital game",
    "interpret the design decisions for the game",
    "improvements to the game based on feedback",
    "comprehensive evaluation of game outputs against original design aims",
    "unit 8 computer game development",
    "computer game development",
    "target audience requirements",
    "client requirements",
    "aged 8 to 12",
    "ages 8 to 12",
    "from 8 to 12 years",
    "8-12 years old",
    "in this assignment you will",
    "in this project you will",
)

# Structural markers — slides, criterion codes, cover sheet lines.
_BOILERPLATE_PATTERNS: Tuple[Pattern[str], ...] = (
    re.compile(r"===\s*Slide\s+\d+\s*===", re.IGNORECASE),
    re.compile(r"\[Layout:\s*[^\]]+\]", re.IGNORECASE),
    re.compile(r"===\s*[^\n]+?\s*\((?:code|image OCR|Vision)\)\s*===", re.IGNORECASE),
    re.compile(r"===\s*تحليل الصور/الفيديو[^\n]*===", re.IGNORECASE),
    re.compile(r"\[PPTX_FILE:[^\]]+\]", re.IGNORECASE),
    re.compile(r"\b8/[A-Z]+\.[A-Z]\d+\b:?", re.IGNORECASE),
    re.compile(r"\b(?:B|C|BC)\.[PMD]\d+\b:?", re.IGNORECASE),
    re.compile(
        r"^\s*(?:الاسم|الموضوع|المدرسة|مدرس المادة|المعلم|الصف|رقم بيرسون|SD|Pearson|"
        r"Name|Subject|School|Teacher|Class)\s*[:：].*$",
        re.MULTILINE | re.IGNORECASE,
    ),
    re.compile(r"^\s*(?:مقدمة|المقدمة|Introduction)\s*$", re.MULTILINE | re.IGNORECASE),
)

# Precompiled phrase patterns (longest first).
_PHRASE_PATTERNS: Tuple[Pattern[str], ...] = tuple(
    re.compile(re.escape(p), re.IGNORECASE) for p in sorted(_BTEC_BOILERPLATE_PHRASES, key=len, reverse=True)
)


def _collapse_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip())


def _normalize_arabic_letters(text: str) -> str:
    """Light normalization for boilerplate-only phrase checks."""
    t = unicodedata.normalize("NFKC", text or "")
    t = re.sub(r"[\u0640]", "", t)
    t = re.sub(r"[إأآا]", "ا", t)
    t = re.sub(r"ى", "ي", t)
    return t


def strip_plagiarism_boilerplate(text: str) -> str:
    """Remove shared BTEC/assignment boilerplate; keep student-owned content."""
    if not text:
        return ""
    out = text
    for pat in _BOILERPLATE_PATTERNS:
        out = pat.sub(" ", out)
    for pat in _PHRASE_PATTERNS:
        out = pat.sub(" ", out)
    return _collapse_whitespace(out)


def is_boilerplate_phrase(phrase: str) -> bool:
    """True when a matched segment is assignment boilerplate, not student prose."""
    if not phrase or len(phrase.strip()) < 6:
        return True
    norm = _normalize_arabic_letters(_collapse_whitespace(phrase).lower())
    for boiler in _BTEC_BOILERPLATE_PHRASES:
        b_norm = _normalize_arabic_letters(boiler.lower())
        if norm in b_norm or b_norm in norm:
            return True
    for pat in _BOILERPLATE_PATTERNS:
        if pat.search(phrase):
            return True
    return False


def filter_boilerplate_phrases(phrases: Iterable[str]) -> List[str]:
    return [p for p in phrases if not is_boilerplate_phrase(p)]
