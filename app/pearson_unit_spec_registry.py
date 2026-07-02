"""
Pearson BTEC Jordan — official unit specification anchors.

Stores frozen criterion metadata per unit so grading can cross-check teacher-uploaded
specs instead of relying on upload alone. Populate `UNIT_SPECS` from approved
Pearson unit assignment briefs / IV packs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.unit_calibration import UNIT9_KEY, to_pearson_registry_entry

REGISTRY_VERSION = "pearson_unit_spec_v1"

# unit_key → {title, criteria: [{code, level, command_verb, evidence_types}]}
UNIT_SPECS: Dict[str, Dict[str, Any]] = {
    UNIT9_KEY: to_pearson_registry_entry(),
    # Alias: Pearson platform uses unit 8 criterion prefix for the same games unit.
    "unit_8_games": to_pearson_registry_entry(),
}


def _normalize_criterion_code(raw: Any) -> str:
    text = str(raw or "").strip().upper()
    if "/" in text:
        text = text.split("/")[-1]
    return text


def lookup_unit_spec(unit_key: str) -> Optional[Dict[str, Any]]:
    key = (unit_key or "").strip().lower().replace(" ", "_")
    if key in UNIT_SPECS:
        return UNIT_SPECS.get(key)
    aliases = {
        "unit9": UNIT9_KEY,
        "unit_9": UNIT9_KEY,
        "unit8": "unit_8_games",
        "unit_8": "unit_8_games",
        "games": UNIT9_KEY,
    }
    return UNIT_SPECS.get(aliases.get(key, key))


def compare_uploaded_criteria_to_official(
    uploaded: List[Dict[str, Any]],
    *,
    unit_key: str,
    brief_only: bool = False,
) -> Dict[str, Any]:
    """
    Diff teacher-uploaded criteria against bundled official spec.
    Returns drift report for IV / audit — does not block grading by itself.
    """
    official = lookup_unit_spec(unit_key)
    if not official:
        return {
            "status": "no_official_anchor",
            "unit_key": unit_key,
            "message_ar": "لا يوجد مرجع رسمي مُخزّن لهذه الوحدة — يعتمد التصحيح على ما رفعه المعلم.",
        }

    official_codes = set()
    for c in official.get("criteria") or []:
        if brief_only and not c.get("in_assignment_brief"):
            continue
        code = _normalize_criterion_code(c.get("platform_level") or c.get("code"))
        if code:
            official_codes.add(code)
    uploaded_codes = set()
    for c in uploaded:
        if not isinstance(c, dict):
            continue
        code = _normalize_criterion_code(c.get("code") or c.get("criteria_level"))
        if code:
            uploaded_codes.add(code)

    missing = sorted(official_codes - uploaded_codes)
    extra = sorted(uploaded_codes - official_codes)

    return {
        "status": "compared",
        "unit_key": unit_key,
        "official_title": official.get("title"),
        "pearson_edition": official.get("pearson_edition"),
        "missing_from_upload": missing,
        "extra_in_upload": extra,
        "aligned": not missing and not extra,
        "message_ar": (
            "المعايير المرفوعة تطابق المرجع الرسمي."
            if not missing and not extra
            else f"انحراف: ناقص {len(missing)} — زائد {len(extra)} عن المرجع الرسمي."
        ),
    }
