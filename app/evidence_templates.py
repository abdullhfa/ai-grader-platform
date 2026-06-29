"""Resolve Pearson BTEC evidence Word templates (IT + LA mapping)."""
from __future__ import annotations

import os
import re
from typing import Dict, List, Optional, Tuple

_TEMPLATE_DIRS = ("uploads/templates", "app/templates")

LA_TEMPLATE_CANDIDATES = [
    "نموذج ربط أدلة المتعلم بأهداف التعلّم.docx",
    "نموذج ربط ادلة المتعلم بأهداف التعلم.docx",
    "la_evidence_template.docx",
    "evidence_la_template.docx",
]

EVIDENCE_IT_BY_LEVEL: Dict[str, List[str]] = {
    "L2": [
        "Evidance - IT - L2.docx",
        "Evidence - IT - L2.docx",
        "Evidance - IT L2.docx",
    ],
    "L3": [
        "Evidance - IT - L3.docx",
        "Evidence - IT - L3.docx",
        "Evidance - IT L3.docx",
    ],
    "DEFAULT": [
        "Evidance - IT.docx",
        "Evidence - IT.docx",
    ],
}


def _exists_in_dirs(filename: str) -> Optional[str]:
    for d in _TEMPLATE_DIRS:
        p = os.path.join(d, filename)
        if os.path.isfile(p):
            return p
    return None


def detect_btec_level_hint(*texts: Optional[str]) -> str:
    """Return L2, L3, or DEFAULT from assignment/batch titles."""
    blob = " ".join(t for t in texts if t).upper()
    if re.search(r"\bL\s*2\b|\bLEVEL\s*2\b|الصف\s*العاشر|العاشر", blob, re.I):
        return "L2"
    if re.search(r"\bL\s*3\b|\bLEVEL\s*3\b|ثانوي|الأول\s*ثانوي|الثاني\s*ثانوي", blob, re.I):
        return "L3"
    return "DEFAULT"


def resolve_la_evidence_template() -> Optional[str]:
    for name in LA_TEMPLATE_CANDIDATES:
        p = _exists_in_dirs(name)
        if p:
            return p
    return None


def resolve_it_evidence_template(level_hint: str = "DEFAULT") -> Optional[str]:
    level = level_hint if level_hint in EVIDENCE_IT_BY_LEVEL else "DEFAULT"
    for name in EVIDENCE_IT_BY_LEVEL[level] + EVIDENCE_IT_BY_LEVEL["DEFAULT"]:
        p = _exists_in_dirs(name)
        if p:
            return p
    return None


def resolve_evidence_templates(
    level_hint: str = "DEFAULT",
) -> Tuple[Optional[str], Optional[str], List[str]]:
    """Return (it_template_path, la_template_path, missing_labels)."""
    missing: List[str] = []
    it_path = resolve_it_evidence_template(level_hint)
    la_path = resolve_la_evidence_template()
    if not it_path:
        if level_hint == "L2":
            missing.append("Evidance - IT - L2.docx (أو Evidance - IT.docx)")
        elif level_hint == "L3":
            missing.append("Evidance - IT - L3.docx (أو Evidance - IT.docx)")
        else:
            missing.append("Evidance - IT.docx")
    if not la_path:
        missing.append("نموذج ربط أدلة المتعلم بأهداف التعلّم.docx")
    return it_path, la_path, missing


def evidence_output_paths(submission_id: int, student_name: str) -> Tuple[str, str]:
    safe = re.sub(r"[^\w\s\u0600-\u06FF-]", "", student_name or "").strip()
    base = os.path.join("uploads", "reports", "evidence_records", "per_student")
    return (
        os.path.join(base, f"evidence_record_sub{submission_id}_{safe}.docx"),
        os.path.join(base, f"la_evidence_sub{submission_id}_{safe}.docx"),
    )


def student_has_evidence_files(submission_id: int, student_name: str) -> bool:
    import glob

    safe = re.sub(r"[^\w\s\u0600-\u06FF-]", "", student_name or "").strip()
    ev_glob = glob.glob(
        os.path.join("uploads", "reports", "evidence_records", "**", f"evidence_record_sub{submission_id}_*.docx"),
        recursive=True,
    )
    la_glob = glob.glob(
        os.path.join("uploads", "reports", "evidence_records", "**", f"la_evidence_sub{submission_id}_*.docx"),
        recursive=True,
    )
    if ev_glob and la_glob:
        return True
    ev1, ev2 = evidence_output_paths(submission_id, student_name)
    return os.path.isfile(ev1) and os.path.isfile(ev2)
