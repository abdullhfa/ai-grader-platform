"""
Isolate student-authored submission text for evidence coverage scoring.

Coverage must not read AI feedback, governance blocks, or generated reports.
"""
from __future__ import annotations

import re
from typing import Optional

# Leading blocks prepended before the AI grader prompt (artifact / runtime / governance).
_PREFIX_MARKERS = (
    "═══════════════════════════════════════════════════════════",
    "[سجل artifacts",
    "[BASIC — سجل artifacts مختصر]",
    "[RUNTIME OBSERVATION",
    "[RUNTIME-EVIDENCE",
    "[AUTHORITY",
    "[GOVERNANCE",
    "[EVIDENCE LINEAGE",
    "[CONSISTENCY",
    "[مرفق تلقائي — تحليل كود",
    "تحليل كود مشروع اللعبة",
)

# Sections that may appear inside bundled text — strip entirely.
_INLINE_STRIP_RE = re.compile(
    r"(?:"
    r"═{3,}[\s\S]*?(?:presence\s*≠\s*authority|runtime evidence governance|سجل artifacts)[\s\S]*?═{3,}"
    r"|BTEC\s+Assignment\s+Grading\s+Report[\s\S]*"
    r"|تقرير\s+تصحيح\s+واجب[\s\S]*"
    r"|تعليق\s+المقيّم:[\s\S]*?(?:\n\n|\Z)"
    r"|FORBIDDEN:[\s\S]*?(?:\n\n|\Z)"
    r"|ALLOWED:[\s\S]*?(?:\n\n|\Z)"
    r"|عبارات\s+مثل\s+«تم\s+التنفيذ[\s\S]*?مستند\s+الطالب\s+الأساسي"
    r"|ما\s+يلي\s+ناتج\s+آلية\s+مساعدة[\s\S]*?(?:\n\n|\Z)"
    r"|تنويه:\s*L4\s*=\s*ملاحظة\s+آلية[\s\S]*?(?:\n\n|\Z)"
    r")",
    re.IGNORECASE,
)


def _strip_leading_grader_prefixes(text: str) -> str:
    t = text or ""
    while t:
        stripped = t.lstrip()
        removed = False
        for marker in _PREFIX_MARKERS:
            if stripped.startswith(marker):
                # Drop through the first blank-line gap after this injected header.
                nl = stripped.find("\n\n")
                stripped = stripped[nl + 2 :] if nl >= 0 else ""
                removed = True
                break
        if not removed:
            break
        t = stripped
    return t


def _clean_student_text(text: str) -> str:
    t = _INLINE_STRIP_RE.sub(" ", text or "")
    t = re.sub(r"\s{2,}", " ", t).strip()
    return t


def isolate_student_submission_text(
    full_text: str,
    *,
    word_only_text: Optional[str] = None,
) -> str:
    """
  Return text suitable for coverage heuristics: student files/docs only.

  Prefer ``word_only_text`` (pure Word/PDF extract) when available.
  """
    if word_only_text:
        w = word_only_text.strip()
        if len(w) >= 40:
            return _clean_student_text(w)

    t = _strip_leading_grader_prefixes(full_text or "")
    return _clean_student_text(t)
