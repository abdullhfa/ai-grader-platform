"""
Extract neutral gameplay requirement checklist from Brief / GDD / Test Plan text.

No criterion mapping here — requirements only (PRO v1).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

CHECKLIST_VERSION = "requirement_checklist_v1"

_REQUIREMENT_PATTERNS: Tuple[Tuple[str, str, str], ...] = (
    ("player_movement", r"player\s*movement|move(?:ment)?\s*(?:the\s*)?player|\bmove\s+(?:left|right|up|down)|حركة\s*اللاعب|تحريك\s*اللاعب", "حركة اللاعب"),
    ("jump", r"\bjump(?:ing)?\b|double\s*jump|قفز|القفز", "القفز"),
    ("collect_items", r"collect(?:ible)?s?|coin|gem|key|pickup|جمع\s*العملات|عملات", "جمع العناصر"),
    ("score_system", r"score\s*system|points?\s*system|\bscore\b|نقاط|نظام\s*النقاط", "نظام النقاط"),
    ("enemy_interaction", r"\benemy\b|opponent|hostile|عدو|خصم", "تفاعل العدو"),
    ("win_condition", r"win\s*condition|victory|finish\s*line|goal\s*reached|شرط\s*الفوز|الفوز", "شرط الفوز"),
    ("lose_condition", r"game\s*over|lose\s*condition|death|player\s*dies|خسارة|نهاية\s*اللعبة", "شرط الخسارة"),
    ("restart", r"restart|retry|respawn|إعادة\s*التشغيل|إعادة\s*المحاولة", "إعادة التشغيل"),
    ("menu_ui", r"main\s*menu|start\s*button|pause\s*menu|قائمة\s*رئيسية", "واجهة / قائمة"),
    ("level_design", r"level\s*design|multiple\s*levels|مستوى|مراحل", "تصميم المستويات"),
)


def _text_blobs(
    *,
    student_text: str = "",
    reference_solution: Optional[Dict[str, Any]] = None,
    extra_texts: Optional[Sequence[str]] = None,
) -> str:
    parts: List[str] = [student_text or ""]
    ref = reference_solution or {}
    for key in (
        "markdown_guide",
        "assignment_brief",
        "brief",
        "mission_text",
        "description",
    ):
        val = ref.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val)
    criteria = ref.get("criteria") or ref.get("grading_criteria")
    if isinstance(criteria, list):
        for row in criteria:
            if isinstance(row, dict):
                for k in ("description", "requirement", "text", "details"):
                    v = row.get(k)
                    if isinstance(v, str) and v.strip():
                        parts.append(v)
    if extra_texts:
        parts.extend(t for t in extra_texts if t)
    try:
        parts.append(json.dumps(ref, ensure_ascii=False)[:120_000])
    except Exception:
        pass
    return "\n".join(parts)


def build_requirement_checklist(
    *,
    student_text: str = "",
    reference_solution: Optional[Dict[str, Any]] = None,
    extra_texts: Optional[Sequence[str]] = None,
) -> Dict[str, Any]:
    blob = _text_blobs(
        student_text=student_text,
        reference_solution=reference_solution,
        extra_texts=extra_texts,
    )
    requirements: List[Dict[str, Any]] = []
    for req_id, pattern, label_ar in _REQUIREMENT_PATTERNS:
        found = bool(re.search(pattern, blob, re.IGNORECASE))
        requirements.append(
            {
                "id": req_id,
                "label_ar": label_ar,
                "mentioned_in_sources": found,
            }
        )
    mentioned = [r["id"] for r in requirements if r["mentioned_in_sources"]]
    if not mentioned:
        requirements = [
            {
                "id": req_id,
                "label_ar": label_ar,
                "mentioned_in_sources": True,
            }
            for req_id, _pat, label_ar in _REQUIREMENT_PATTERNS[:6]
        ]
        mentioned = [r["id"] for r in requirements]

    return {
        "version": CHECKLIST_VERSION,
        "requirements": requirements,
        "requirement_ids": mentioned,
        "source_chars_scanned": len(blob),
        "disclaimer_ar": (
            "قائمة متطلبات مستخرجة من النصوص فقط — لا تُعد تحقيقاً للمعايير."
        ),
    }
