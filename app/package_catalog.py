"""Pearson BTEC subscription packages — canonical catalog for UI and DB sync."""
from __future__ import annotations

from typing import Any, Dict, List

# Teacher / schools — English tier names (marketing order).
PACKAGE_CATALOG: List[Dict[str, Any]] = [
    {"name": "Basic", "price": 5.0, "assignment_limit": 4, "is_featured": False, "theme": 0},
    {"name": "Standard", "price": 10.0, "assignment_limit": 10, "is_featured": False, "theme": 1},
    {"name": "Premium", "price": 25.0, "assignment_limit": 30, "is_featured": True, "theme": 2},
    {"name": "Pro", "price": 28.0, "assignment_limit": 35, "is_featured": False, "theme": 3},
    {"name": "Enterprise", "price": 33.0, "assignment_limit": 50, "is_featured": False, "theme": 4},
    {"name": "Trial", "price": 4.0, "assignment_limit": 2, "is_featured": False, "theme": 0},
    {"name": "Starter", "price": 15.0, "assignment_limit": 30, "is_featured": False, "theme": 1},
    {"name": "Advanced", "price": 25.0, "assignment_limit": 50, "is_featured": True, "theme": 2},
    {"name": "Ultimate", "price": 40.0, "assignment_limit": 100, "is_featured": False, "theme": 3},
]

# Student audience — same tier naming; DB name prefixed to stay unique.
STUDENT_PACKAGE_CATALOG: List[Dict[str, Any]] = [
    {
        "name": "Student Basic",
        "card_title": "Basic",
        "subtitle": "2 واجبات لمهمة واحدة",
        "price": 5.0,
        "assignment_limit": 2,
        "is_featured": False,
        "theme": 0,
    },
    {
        "name": "Student Standard",
        "card_title": "Standard",
        "subtitle": "6 واجبات لمهمتين",
        "price": 10.0,
        "assignment_limit": 6,
        "is_featured": False,
        "theme": 1,
    },
    {
        "name": "Student Premium",
        "card_title": "Premium",
        "subtitle": "8 واجبات لمهمة واحدة",
        "price": 12.0,
        "assignment_limit": 8,
        "is_featured": True,
        "theme": 2,
    },
    {
        "name": "Student Pro",
        "card_title": "Pro",
        "subtitle": "14 واجبات لمهمتين",
        "price": 18.0,
        "assignment_limit": 14,
        "is_featured": False,
        "theme": 3,
    },
]

ALL_PACKAGE_CATALOGS: List[Dict[str, Any]] = PACKAGE_CATALOG + STUDENT_PACKAGE_CATALOG


def assignment_subtitle(limit: int) -> str:
    """Subtitle under package name: «تصحيح N واجب/واجبات»."""
    if limit in (4, 10):
        word = "واجبات"
    else:
        word = "واجب"
    return f"تصحيح {limit} {word}"


# Shared BTEC Pearson feature bullets (after the assignment-count line).
_BTEC_FEATURE_BULLETS: List[str] = [
    "شرح تفصيلي للمهمة مع ذكر أمثلة عليها وفق معايير ومتطلبات BTEC بيرسون",
    "إنشاء سجلات التقييم الرسمية (Assessment Record, IV Assessment, IV Decisions) وفق متطلبات ومعايير بيرسون بشكل دقيق",
    "ذكر المعايير التي أنجزها الطالب والتي لم ينجزها وفق متطلبات BTEC بيرسون",
    "تقارير مفصلة عن نقاط القوة والضعف في واجب الطالب",
    "تحديد نسبة استخدام الذكاء الاصطناعي في واجبات الطلبة",
    "تحديد نسبة التشابه بين واجبات الطلبة",
]


def package_feature_lines(limit: int) -> List[str]:
    """Seven feature bullets shown on every package card."""
    return [
        f"تصحيح عدد {limit} واجبات للطلبة بشكل مفصل وفق معايير ومتطلبات BTEC بيرسون",
        *_BTEC_FEATURE_BULLETS,
    ]


_STUDENT_EXCLUDED_FEATURES = {
    "إنشاء سجلات التقييم الرسمية (Assessment Record, IV Assessment, IV Decisions) وفق متطلبات ومعايير بيرسون بشكل دقيق",
}


def student_package_feature_lines(limit: int) -> List[str]:
    """Feature bullets for student cards (no official assessment-record exports)."""
    return [
        line
        for line in package_feature_lines(limit)
        if line not in _STUDENT_EXCLUDED_FEATURES
    ]
