"""Shared criterion matching for calibration package (avoids import cycles)."""
from __future__ import annotations


def criteria_match(level: str, gold_crit: str) -> bool:
    g = (gold_crit or "").strip().upper()
    l = (level or "").strip().upper()
    if not g or not l:
        return False
    if l == g or l.endswith("." + g):
        return True
    short = l.split(".")[-1] if "." in l else l
    return short == g
