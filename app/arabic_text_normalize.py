"""
Lightweight Arabic normalization for coverage synonym matching (not NLP).
"""
from __future__ import annotations

import re

_ALEF_VARIANTS_RE = re.compile("[إأآٱا]")
_YA_VARIANTS_RE = re.compile("ى")
_TA_MARBUTA_RE = re.compile("ة")
_HAMZA_VARIANTS_RE = re.compile("[ؤئ]")
_DIACRITICS_RE = re.compile(r"[\u064B-\u065F\u0670]")
_TATWEEL_RE = re.compile("ـ")


def normalize_arabic_text(text: str) -> str:
    """Unify common spelling variants for dictionary matching."""
    t = text or ""
    t = _DIACRITICS_RE.sub("", t)
    t = _TATWEEL_RE.sub("", t)
    t = _ALEF_VARIANTS_RE.sub("ا", t)
    t = _YA_VARIANTS_RE.sub("ي", t)
    t = _TA_MARBUTA_RE.sub("ه", t)
    t = _HAMZA_VARIANTS_RE.sub("", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip().lower()
