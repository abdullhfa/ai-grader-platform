"""
Pearson BTEC Jordan — official unit specification anchors.

Stores frozen criterion metadata per unit so grading can cross-check teacher-uploaded
specs instead of relying on upload alone. Populate `UNIT_SPECS` from approved
Pearson unit assignment briefs / IV packs.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

REGISTRY_VERSION = "pearson_unit_spec_v1"

# unit_key → {title, criteria: [{code, level, command_verb, evidence_types}]}
UNIT_SPECS: Dict[str, Dict[str, Any]] = {
    # Example shape — extend with approved Pearson unit packs:
    # "unit_6_games": {
    #     "title": "Unit 6: Games Development",
    #     "pearson_edition": "2024",
    #     "criteria": [
    #         {"code": "B.P3", "level": "P", "command_verb": "Produce", ...},
    #     ],
    # },
}


def lookup_unit_spec(unit_key: str) -> Optional[Dict[str, Any]]:
    key = (unit_key or "").strip().lower().replace(" ", "_")
    return UNIT_SPECS.get(key)


def compare_uploaded_criteria_to_official(
    uploaded: List[Dict[str, Any]],
    *,
    unit_key: str,
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

    official_codes = {
        str(c.get("code") or "").strip().upper()
        for c in official.get("criteria") or []
        if c.get("code")
    }
    uploaded_codes = {
        str(c.get("code") or c.get("criteria_level") or "").strip().upper()
        for c in uploaded
        if isinstance(c, dict)
    }
    uploaded_codes = {c for c in uploaded_codes if c}

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
