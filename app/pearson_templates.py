"""Pearson BTEC template discovery — Assessment Record, IV Brief, IV Decisions, Evidence."""
from __future__ import annotations

import os
import re
from typing import Any, Dict, List, Optional, Tuple

from app.evidence_templates import (  # type: ignore
    detect_btec_level_hint,
    resolve_evidence_templates,
)

_TEMPLATE_DIRS = ("uploads/templates", "app/templates")

ASSESSMENT_RECORD_CANDIDATES = [
    "assessment_record_template.docx",
    "Assessment Record template.docx",
]

IV_BRIEF_CANDIDATES = [
    "iv_assignment_brief_template.docx",
]

IV_DECISIONS_CANDIDATES = [
    "iv_assessment_decisions_template.docx",
    "BTEC IV Assessment Decisions.docx",
    "IV Assessment Decisions template.docx",
    "iv_assessment_decisions.docx",
]


def _exists_in_dirs(filename: str) -> Optional[str]:
    for d in _TEMPLATE_DIRS:
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    return None


def _resolve_first(candidates: List[str]) -> Optional[str]:
    for name in candidates:
        p = _exists_in_dirs(name)
        if p:
            return p
    return None


def resolve_assessment_record_template() -> Optional[str]:
    return _resolve_first(ASSESSMENT_RECORD_CANDIDATES)


def resolve_iv_brief_template() -> Optional[str]:
    return _resolve_first(IV_BRIEF_CANDIDATES)


def resolve_iv_decisions_template() -> Optional[str]:
    return _resolve_first(IV_DECISIONS_CANDIDATES)


def pearson_templates_status(level_hint: str = "DEFAULT") -> Dict[str, Any]:
    """Return readiness of all Pearson export templates."""
    ar = resolve_assessment_record_template()
    ivb = resolve_iv_brief_template()
    ivd = resolve_iv_decisions_template()
    ev_it, ev_la, ev_missing = resolve_evidence_templates(level_hint)

    items = [
        {
            "key": "assessment_record",
            "label_ar": "BTEC Assessment Record",
            "label_en": "Assessment Record template.docx",
            "path": ar,
            "ready": bool(ar),
        },
        {
            "key": "iv_brief",
            "label_ar": "BTEC IV of Assignment Brief",
            "label_en": "iv_assignment_brief_template.docx",
            "path": ivb,
            "ready": bool(ivb),
        },
        {
            "key": "iv_decisions",
            "label_ar": "BTEC IV Assessment Decisions",
            "label_en": "iv_assessment_decisions_template.docx",
            "path": ivd,
            "ready": bool(ivd),
        },
        {
            "key": "evidence_it",
            "label_ar": "Evidance - IT (Pearson Evidence)",
            "label_en": "Evidance - IT - L2.docx / Evidance - IT.docx",
            "path": ev_it,
            "ready": bool(ev_it),
        },
        {
            "key": "evidence_la",
            "label_ar": "نموذج ربط أدلة المتعلم بأهداف التعلّم",
            "label_en": "LA evidence mapping",
            "path": ev_la,
            "ready": bool(ev_la),
        },
    ]
    missing = [i["label_ar"] for i in items if not i["ready"]]
    if ev_missing:
        for m in ev_missing:
            if m not in missing:
                missing.append(m)

    return {
        "level_hint": level_hint,
        "items": items,
        "ready_count": sum(1 for i in items if i["ready"]),
        "total_count": len(items),
        "all_ready": all(i["ready"] for i in items),
        "missing": missing,
    }


def resolve_for_assignment(
    assignment_title: str = "",
    unit_name: str = "",
    unit_info: str = "",
) -> Dict[str, Any]:
    level = detect_btec_level_hint(assignment_title, unit_name, unit_info)
    status = pearson_templates_status(level)
    return {
        "level_hint": level,
        "assessment_record": resolve_assessment_record_template(),
        "iv_brief": resolve_iv_brief_template(),
        "iv_decisions": resolve_iv_decisions_template(),
        "evidence_it": status["items"][3]["path"],
        "evidence_la": status["items"][4]["path"],
        "status": status,
    }
