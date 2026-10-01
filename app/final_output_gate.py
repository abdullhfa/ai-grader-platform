"""Central finalization gate: a grade is only exported/shown as FINAL when allowed.

``Cannot Run != Not Achieved`` also holds at the output boundary.  While a
result is PAUSED / PROVISIONAL (``assessment_state``) or ``final_grade_allowed``
is False, the provisional grade stays INTERNAL (snapshot, ``grade_level_provisional``)
so the process can resume, but every final output — Word, PDF, DB summary, LMS
export, batch listings — shows a withheld marker instead of a grade.

Results without an ``assessment_state`` (non-game or legacy stored data) are
unaffected: the gate never invents a block.
"""
from __future__ import annotations

from typing import Any, Mapping, Optional

WITHHELD_GRADE = "PAUSED"
WITHHELD_LABEL = "لا درجة نهائية — التصحيح موقوف (PAUSED)"
_NON_FINAL_STATES = {"PAUSED", "PROVISIONAL"}
_NON_FINAL_DECISIONS = {"PAUSED", "PROVISIONAL_BLOCKED"}


def final_grade_allowed(record: Optional[Mapping[str, Any]]) -> bool:
    """False when the record is PAUSED/PROVISIONAL or says final_grade_allowed=False."""
    if not isinstance(record, Mapping):
        return True
    if record.get("final_grade_allowed") is False:
        return False
    state = record.get("assessment_state")
    if isinstance(state, Mapping):
        if state.get("state") in _NON_FINAL_STATES or state.get("final_grade_allowed") is False:
            return False
    return record.get("grade_decision_status") not in _NON_FINAL_DECISIONS


def summary_grade(record: Optional[Mapping[str, Any]], grade: Any) -> Any:
    """Grade value that may be written to a DB summary / final output."""
    return grade if final_grade_allowed(record) else WITHHELD_GRADE


def output_grade_label(record: Optional[Mapping[str, Any]], label: Any) -> Any:
    """Display label for Word/PDF/listings: the withheld marker while not final."""
    return label if final_grade_allowed(record) else WITHHELD_LABEL
