"""
Append observer role drift check responses — observational posture only.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_ID = "OBSERVER_ROLE_DRIFT_CHECK_v1"
INSTITUTIONAL_INVARIANT_EN = (
    "The system may notice epistemic escalation. "
    "It may not silently conclude it."
)
INSTITUTIONAL_INVARIANT_AR = (
    "النظام قد يلاحظ تصعيدًا معرفيًا. "
    "لا يجوز أن يستنتجه بصمت."
)
OBSERVABILITY_INVARIANT_EN = (
    "Observability may illuminate authority formation. "
    "It may not silently inherit authority formation."
)
OBSERVABILITY_INVARIANT_AR = (
    "الرصد قد يُضيء تشكّل السلطة. "
    "لا يجوز أن يرث تشكّل السلطة بصمت."
)

EPISTEMIC_REFUSAL_INVARIANT_EN = (
    "The observer must always remain capable of "
    "epistemic refusal without institutional friction."
)
EPISTEMIC_REFUSAL_INVARIANT_AR = (
    "يجب أن يبقى المراقب قادرًا دائمًا على "
    "الامتناع المعرفي دون احتكاك مؤسسي."
)

LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "observer_role_drift_checks.jsonl"
)

VALID_QUESTION_SETS = frozenset({"baseline", "first_live_vocabulary_hint"})


def append_drift_check(
    record: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
) -> str:
    """Persist facilitator posture review — not a score."""
    path = ledger_path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "check_id": f"ordc_{uuid.uuid4().hex[:12]}",
        "artifact_id": ARTIFACT_ID,
        "logged_at": datetime.datetime.utcnow().isoformat() + "Z",
        "institutional_invariant_en": INSTITUTIONAL_INVARIANT_EN,
        "observability_invariant_en": OBSERVABILITY_INVARIANT_EN,
        "epistemic_refusal_invariant_en": EPISTEMIC_REFUSAL_INVARIANT_EN,
        "assigns_authority": False,
        **record,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["check_id"]


def normalize_drift_responses(
    *,
    question_set: str,
    responses: List[Dict[str, Any]],
    submission_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    session_label: str = "",
    facilitator_notes_ar: str = "",
) -> Dict[str, Any]:
    if question_set not in VALID_QUESTION_SETS:
        raise ValueError(f"invalid question_set: {question_set}")
    return {
        "question_set": question_set,
        "submission_id": submission_id,
        "batch_id": batch_id,
        "session_label": session_label or None,
        "responses": responses,
        "facilitator_notes_ar": facilitator_notes_ar or "",
        "not": ["grading", "compliance_score", "facilitator_ranking"],
    }
