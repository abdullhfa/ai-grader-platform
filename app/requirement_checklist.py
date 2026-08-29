"""
Extract neutral gameplay requirement checklist from Brief / GDD / Test Plan text.

No criterion mapping here — requirements only (PRO v1).
"""
from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple

CHECKLIST_VERSION = "requirement_checklist_v2"

_REQUIREMENT_PATTERNS: Tuple[Tuple[str, str, str], ...] = (
    ("player_movement", r"player\s*movement|move(?:ment)?\s*(?:the\s*)?player|\bmove\s+(?:left|right|up|down)|حركة\s*اللاعب|تحريك\s*اللاعب", "حركة اللاعب"),
    (
        "jump",
        r"\bjump(?:ing)?\b|double\s*jump|(?<!\w)(?:قفز|القفز)(?!\w)",
        "القفز",
    ),
    ("collect_items", r"collect(?:ible)?s?|coin|gem|key|pickup|جمع\s*(?:العملات|العناصر)|التقاط|عملات", "جمع العناصر"),
    ("score_system", r"score\s*system|points?\s*system|\bscore\b|نقاط|نظام\s*النقاط", "نظام النقاط"),
    ("enemy_interaction", r"\benemy\b|opponent|hostile|hazards?|obstacles?|عدو|خصم|مخاطر|عقبات", "تفاعل العدو"),
    ("lives_system", r"lives?\s*system|player\s*lives|health\s*system|hearts?|نظام\s*(?:الأرواح|الحياة)|الأرواح|قلوب", "نظام الأرواح"),
    ("timer_system", r"timer|time\s*limit|countdown|timed\s*game|مؤقت|عداد\s*زمني|وقت\s*محدد|لعبة\s*مؤقتة", "المؤقت الزمني"),
    ("difficulty_levels", r"difficulty\s*levels?|easy\s*/\s*medium\s*/\s*hard|(?:مستوى|مستويات)\s*(?:ال)?صعوبة|(?:درجة|درجات)\s*(?:ال)?صعوبة|سهل\s*/\s*متوسط\s*/\s*صعب", "مستويات الصعوبة"),
    ("win_condition", r"win\s*condition|victory|finish\s*line|goal\s*reached|شرط\s*الفوز|الفوز", "شرط الفوز"),
    ("lose_condition", r"game\s*over|lose\s*condition|death|player\s*dies|خسارة|نهاية\s*اللعبة", "شرط الخسارة"),
    ("restart", r"restart|retry|respawn|إعادة\s*(?:ال)?تشغيل|إعادة\s*(?:ال)?محاولة", "إعادة التشغيل"),
    ("menu_ui", r"main\s*menu|start\s*button|pause\s*menu|قائمة\s*رئيسية", "واجهة / قائمة"),
    ("level_design", r"level\s*design|multiple\s*levels|مستو(?:ى|يات|يين?)|مراحل", "تصميم المستويات"),
)

_JUMP_NEGATION = re.compile(
    r"(?:\b(?:no|not|cannot|can't|does\s+not|doesn't|without)\b[^.!?،؛\n]{0,28}"
    r"|(?:لا\s+(?:يمكن(?:ه|ها)?|يستطيع|تستطيع)|غير\s+قابل(?:ة)?|بدون)\s*[^.!?،؛\n]{0,20})$",
    re.IGNORECASE,
)


def _jump_applicability(blob: str, pattern: str) -> tuple[bool, bool]:
    """Return (positive, explicitly_not_applicable) for real jump mentions."""
    positive = False
    negated = False
    for match in re.finditer(pattern, blob, re.IGNORECASE):
        prefix = blob[max(0, match.start() - 50) : match.start()]
        if _JUMP_NEGATION.search(prefix):
            negated = True
        else:
            positive = True
    return positive, bool(negated and not positive)


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
        explicitly_not_applicable = False
        if req_id == "jump":
            found, explicitly_not_applicable = _jump_applicability(blob, pattern)
        else:
            found = bool(re.search(pattern, blob, re.IGNORECASE))
        requirements.append(
            {
                "id": req_id,
                "label_ar": label_ar,
                "mentioned_in_sources": found,
                "applicability": (
                    "required"
                    if found
                    else "not_applicable"
                    if explicitly_not_applicable
                    else "not_mentioned"
                ),
            }
        )
    mentioned = [r["id"] for r in requirements if r["mentioned_in_sources"]]
    if not mentioned:
        fallback_ids = {
            req_id
            for req_id, _pat, _label_ar in _REQUIREMENT_PATTERNS[:6]
            if not any(
                row["id"] == req_id and row.get("applicability") == "not_applicable"
                for row in requirements
            )
        }
        for row in requirements:
            if row["id"] in fallback_ids:
                row["mentioned_in_sources"] = True
                row["applicability"] = "required"
        mentioned = [r["id"] for r in requirements if r["mentioned_in_sources"]]

    return {
        "version": CHECKLIST_VERSION,
        "requirements": requirements,
        "requirement_ids": mentioned,
        "source_chars_scanned": len(blob),
        "disclaimer_ar": (
            "قائمة متطلبات مستخرجة من النصوص فقط — لا تُعد تحقيقاً للمعايير."
        ),
    }
