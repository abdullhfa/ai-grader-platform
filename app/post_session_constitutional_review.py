"""
Post-session constitutional review — append-only, not grading.
"""
from __future__ import annotations

import datetime
import json
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

ARTIFACT_ID = "POST_SESSION_CONSTITUTIONAL_REVIEW_v1"
LEDGER = (
    Path(__file__).resolve().parent
    / "calibration"
    / "human_cohort_workshop"
    / "post_session_constitutional_reviews.jsonl"
)


def append_post_session_review(
    record: Dict[str, Any],
    *,
    ledger_path: Optional[Path] = None,
) -> str:
    path = ledger_path or LEDGER
    path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "review_id": f"pscr_{uuid.uuid4().hex[:12]}",
        "artifact_id": ARTIFACT_ID,
        "logged_at": datetime.datetime.utcnow().isoformat() + "Z",
        "assigns_authority": False,
        **record,
    }
    with path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry["review_id"]


def normalize_review(
    *,
    cohort_id: str,
    session_label: str,
    facilitator_notes_ar: str = "",
    answers: Optional[List[Dict[str, Any]]] = None,
    organizing_cognition_detected: Optional[bool] = None,
    submission_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    return {
        "cohort_id": cohort_id,
        "session_label": session_label,
        "submission_ids": submission_ids or [],
        "answers": answers or [],
        "organizing_cognition_detected": organizing_cognition_detected,
        "facilitator_notes_ar": facilitator_notes_ar or "",
        "recommended_action_if_organizing": "reduce_instrumentation_not_expand",
    }
