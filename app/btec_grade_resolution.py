"""
BTEC institutional grade resolution — single source of truth (SSOT).

All official D/M/P/U band decisions must go through ``determine_grade_level``.
Display layers (institutional_grade_resolution, expected_runtime_grade) read
``grade_level`` from the grading snapshot; they must not re-derive bands independently.
"""
from __future__ import annotations

import re
from typing import Any, Dict, List

_BTEC_GRADE_RE = re.compile(r"\b([DMPU])\b", re.IGNORECASE)


def parse_btec_grade_short(grade_level: str) -> str:
    """Normalize stored grade_level to a single letter: D, M, P, or U."""
    raw = (grade_level or "").strip().upper()
    if not raw:
        return "U"
    m = _BTEC_GRADE_RE.search(raw)
    if m:
        return m.group(1).upper()
    if raw.startswith("D"):
        return "D"
    if raw.startswith("M"):
        return "M"
    if raw.startswith("P"):
        return "P"
    return "U"


def determine_grade_level(criteria_results: List[Dict[str, Any]]) -> str:
    """
    BTEC Pearson institutional award band from achieved criteria.
    Returns D, M, P, or U (Pass band incomplete => U).
    """
    if not criteria_results:
        return "U"

    def short_level(lv: str) -> str:
        return lv.split(".")[-1] if "." in lv else lv

    all_p: List[Dict[str, Any]] = []
    all_m: List[Dict[str, Any]] = []
    all_d: List[Dict[str, Any]] = []

    for r in criteria_results:
        if not isinstance(r, dict):
            continue
        sl = short_level(str(r.get("criteria_level") or "")).upper()
        if sl.startswith("P"):
            all_p.append(r)
        elif sl.startswith("M"):
            all_m.append(r)
        elif sl.startswith("D"):
            all_d.append(r)

    all_p_achieved = len(all_p) > 0 and all(r.get("achieved") for r in all_p)
    all_m_achieved = len(all_m) > 0 and all(r.get("achieved") for r in all_m)
    all_d_achieved = len(all_d) > 0 and all(r.get("achieved") for r in all_d)

    if all_p_achieved and all_m_achieved and all_d_achieved:
        return "D"
    if all_p_achieved and all_m_achieved:
        return "M"
    if all_p_achieved:
        return "P"
    return "U"
