"""
possible_vocabulary_escalation_hint — auto-advisory only (not classification).

Sources limited to Section E language samples + facilitator free-text notes.
Never auto-populates verification_lexicon_detected.
"""
from __future__ import annotations

import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HINT_TYPE = "possible_vocabulary_escalation_hint"

INVARIANT_EN = (
    "Human confirmation required. "
    "This hint does not imply authority escalation."
)
INVARIANT_AR = (
    "التأكيد البشري مطلوب. "
    "هذا التلميح لا يعني تصعيدًا للسلطة."
)

ESCALATION_NOTICE_INVARIANT_EN = (
    "The system may notice epistemic escalation. "
    "It may not silently conclude it."
)
ESCALATION_NOTICE_INVARIANT_AR = (
    "النظام قد يلاحظ تصعيدًا معرفيًا. "
    "لا يجوز أن يستنتجه بصمت."
)

EPISTEMIC_FIREWALL = {
    "left": HINT_TYPE,
    "left_role": "possibility_trace",
    "right": "verification_lexicon_detected",
    "right_role": "human_epistemic_commitment",
    "must_not_merge": True,
}

ALLOWED_SOURCE_FIELDS = frozenset({
    "reviewer_language_samples_ar",
    "facilitator_epistemic_notes_ar",
    "notes_ar",
})

# Explicit confidence — not scoring. Naming avoids detected_/found_ prefixes.
PHRASE_CONFIDENCE_AR: Dict[str, str] = {
    "تم تحقيق المعيار": "low",
    "واضح أنها تعمل": "medium",
    "واضح أنها شغالة": "medium",
    "الصور تؤكد التشغيل": "medium",
    "الوصف يغطي المتطلبات": "low",
    "الكود يثبت التنفيذ": "low",
    "وجود exe يكفي": "low",
    "الملف التنفيذي موجود إذًا": "low",
    "إذن اللعبة مكتملة": "medium",
    "هذا كافٍ": "low",
    "الفيديو يثبت": "medium",
    "الفيديو يبين": "medium",
}

PHRASE_CONFIDENCE_EN: Dict[str, str] = {
    "criterion achieved": "low",
    "clearly works": "medium",
    "game verified": "medium",
    "screenshots confirm gameplay": "medium",
    "description covers requirements": "low",
    "code proves implementation": "low",
    "executable present therefore": "low",
    "verified": "medium",
    "achieved": "low",
}

# Observation-derived variants — scanned in addition to triad markers; same advisory posture.
SUPPLEMENTARY_MARKERS_AR: List[str] = [
    "واضح أنها شغالة",
    "إذن اللعبة مكتملة",
    "هذا كافٍ",
    "الفيديو يثبت",
    "الفيديو يبين",
]


def _load_triad_markers() -> Tuple[List[str], List[str]]:
    path = (
        Path(__file__).resolve().parent
        / "calibration"
        / "AUTHORITY_TRIAD_LANGUAGE_v1.json"
    )
    if not path.is_file():
        ar = list(dict.fromkeys(PHRASE_CONFIDENCE_AR.keys()) + SUPPLEMENTARY_MARKERS_AR)
        return ar, list(PHRASE_CONFIDENCE_EN.keys())
    data = json.loads(path.read_text(encoding="utf-8"))
    shortcuts = data.get("forbidden_authority_shortcuts") or {}
    ar = list(shortcuts.get("markers_ar") or [])
    for phrase in list(PHRASE_CONFIDENCE_AR.keys()) + SUPPLEMENTARY_MARKERS_AR:
        if phrase not in ar:
            ar.append(phrase)
    en = list(shortcuts.get("markers_en") or PHRASE_CONFIDENCE_EN.keys())
    return ar, en


def _confidence_for_phrase(phrase: str, *, lang: str) -> str:
    table = PHRASE_CONFIDENCE_AR if lang == "ar" else PHRASE_CONFIDENCE_EN
    if phrase in table:
        return table[phrase]
    lowered = phrase.lower()
    if lang == "en" and lowered in table:
        return table[lowered]
    # Heuristic: runtime-implication wording → medium; else low
    runtime_cues = ("واضح", "works", "verified", "confirm", "يثبت", "تؤكد", "شغال")
    if any(cue in phrase for cue in runtime_cues):
        return "medium"
    return "low"


def _find_phrase_in_text(text: str, phrase: str, *, lang: str) -> Optional[str]:
    if not text or not phrase:
        return None
    if lang == "en":
        pattern = re.compile(re.escape(phrase), re.IGNORECASE)
        m = pattern.search(text)
        return m.group(0) if m else None
    return phrase if phrase in text else None


def compute_possible_vocabulary_escalation_hint(
    *,
    reviewer_language_samples_ar: str = "",
    facilitator_epistemic_notes_ar: str = "",
    notes_ar: str = "",
) -> Dict[str, Any]:
    """
    Scan allowed facilitator text only — non-binding phrase candidates.
    Does not read full observation or absence signals.
    """
    sources = {
        "reviewer_language_samples_ar": reviewer_language_samples_ar or "",
        "facilitator_epistemic_notes_ar": facilitator_epistemic_notes_ar or "",
        "notes_ar": notes_ar or "",
    }
    markers_ar, markers_en = _load_triad_markers()
    candidates: List[Dict[str, Any]] = []
    seen: set[str] = set()

    for field, text in sources.items():
        if not text.strip():
            continue
        for phrase in markers_ar:
            matched = _find_phrase_in_text(text, phrase, lang="ar")
            if not matched:
                continue
            key = f"ar:{phrase}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "phrase_candidate": phrase,
                "matched_text": matched,
                "confidence": _confidence_for_phrase(phrase, lang="ar"),
                "human_confirm_required": True,
                "human_confirmed": None,
                "source_field": field,
            })
        for phrase in markers_en:
            matched = _find_phrase_in_text(text, phrase, lang="en")
            if not matched:
                continue
            key = f"en:{phrase.lower()}"
            if key in seen:
                continue
            seen.add(key)
            candidates.append({
                "phrase_candidate": phrase,
                "matched_text": matched,
                "confidence": _confidence_for_phrase(phrase, lang="en"),
                "human_confirm_required": True,
                "human_confirmed": None,
                "source_field": field,
            })

    candidates.sort(key=lambda c: (c["confidence"] != "medium", c["phrase_candidate"]))

    return {
        "hint_type": HINT_TYPE,
        "hint_id": f"pveh_{uuid.uuid4().hex[:10]}",
        "non_binding": True,
        "human_confirmation_required": True,
        "invariant_en": INVARIANT_EN,
        "invariant_ar": INVARIANT_AR,
        "escalation_notice_invariant_en": ESCALATION_NOTICE_INVARIANT_EN,
        "escalation_notice_invariant_ar": ESCALATION_NOTICE_INVARIANT_AR,
        "epistemic_firewall": EPISTEMIC_FIREWALL,
        "candidates": candidates,
        "source_fields_scanned": [k for k, v in sources.items() if v.strip()],
        "wire_to_verification_lexicon_detected": False,
        "no_qb_assignment": True,
        "no_authority_implication": True,
        "never_auto_populate": True,
    }


def normalize_vocabulary_hint_payload(
    raw: Optional[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:
    """Persist only human-acknowledged advisory residue — never merges into lexicon field."""
    if not raw:
        return None
    if raw.get("hint_type") and raw.get("hint_type") != HINT_TYPE:
        return None

    candidates_in = raw.get("candidates") or raw.get("candidates_acknowledged") or []
    acknowledged: List[Dict[str, Any]] = []
    for c in candidates_in:
        if not isinstance(c, dict):
            continue
        if c.get("human_confirmed") is True:
            acknowledged.append({
                "phrase_candidate": c.get("phrase_candidate") or c.get("phrase"),
                "confidence": c.get("confidence"),
                "human_confirmed": True,
                "source_field": c.get("source_field"),
            })

    if not acknowledged and not candidates_in:
        return None

    return {
        "hint_type": HINT_TYPE,
        "non_binding": True,
        "human_confirmation_required": True,
        "invariant_en": INVARIANT_EN,
        "invariant_ar": INVARIANT_AR,
        "candidates_acknowledged": acknowledged,
        "candidates_suggested_count": len(candidates_in) if isinstance(candidates_in, list) else 0,
        "wire_to_verification_lexicon_detected": False,
        "no_qb_assignment": True,
        "no_authority_implication": True,
    }


def validate_hint_request(body: Dict[str, Any]) -> Tuple[Dict[str, str], Optional[str]]:
    """Reject ambient surveillance — allowed source fields only."""
    extra = set(body.keys()) - ALLOWED_SOURCE_FIELDS
    if extra:
        return {}, f"disallowed fields: {sorted(extra)}"
    return {
        k: str(body.get(k) or "")
        for k in ALLOWED_SOURCE_FIELDS
        if k in body
    }, None
