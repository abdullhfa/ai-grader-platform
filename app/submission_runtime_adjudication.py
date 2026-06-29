"""
Persist runtime criterion adjudication from grading_snapshot to DB records.

Updates C.P5/C.P6 GradingResult rows and GradingSummary after L5 human playtest.
Does not auto-apply without human_playtest_verified unless explicitly overridden.
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from app.models import GradingCriteria, GradingResult, GradingSummary, Submission
from app.runtime_criterion_mapping import (
    apply_runtime_criterion_adjudication,
    is_execution_criterion,
    observation_allows_adjudication,
)


def _criteria_level_match(stored_level: str, target_level: str) -> bool:
    stored = (stored_level or "").strip().upper()
    target = (target_level or "").strip().upper()
    if not stored or not target:
        return False
    if stored == target:
        return True
    stored_short = stored.split(".")[-1]
    target_short = target.split(".")[-1]
    return stored_short == target_short


def _find_db_result_for_criterion(
    db_results: List[GradingResult],
    criteria_level: str,
) -> Optional[GradingResult]:
    for row in db_results:
        crit = row.criteria
        if crit and _criteria_level_match(str(crit.criteria_level or ""), criteria_level):
            return row
    return None


def sync_runtime_adjudication_to_db(
    db: Session,
    submission: Submission,
    grading_snapshot: Dict[str, Any],
    *,
    require_human_playtest: bool = True,
) -> Dict[str, Any]:
    """
    Apply runtime adjudication in snapshot to GradingResult / GradingSummary.

    Returns summary of DB changes (read-only audit for teacher UI).
    """
    inv = grading_snapshot.get("artifact_inventory") or {}
    obs = inv.get("runtime_observation_report") or {}
    if not observation_allows_adjudication(obs, inv):
        return {"applied": False, "reason": "no_runtime_observation"}

    human_ok = bool(
        obs.get("human_playtest_verified")
        or grading_snapshot.get("l5_human_playtest", {}).get("verified")
    )
    if require_human_playtest and not human_ok:
        return {
            "applied": False,
            "reason": "human_playtest_required",
            "message_ar": "يلزم إنهاء Manual Playtest (L5) قبل تطبيق adjudication على الدرجات.",
        }

    working = dict(grading_snapshot)
    adj = apply_runtime_criterion_adjudication(
        working,
        observation=obs,
        inventory=inv,
    )
    if not adj.get("applied"):
        return {"applied": False, "reason": adj.get("reason", "adjudication_skipped")}

    criteria_results = working.get("criteria_results") or []
    if not criteria_results:
        return {
            "applied": False,
            "reason": "no_criteria_results_in_snapshot",
            "message_ar": "لا criteria_results في snapshot — أعد التصحيح أو طبّق من batch حديث.",
        }

    db_results = (
        db.query(GradingResult)
        .filter(GradingResult.submission_id == submission.id)
        .all()
    )
    if not db_results:
        return {
            "applied": False,
            "reason": "no_db_grading_results",
            "message_ar": "لا سجلات GradingResult — التسليم لم يُصحَّح بعد.",
        }

    row_changes: List[Dict[str, Any]] = []
    for cr in criteria_results:
        if not isinstance(cr, dict):
            continue
        level = str(cr.get("criteria_level") or "")
        if not is_execution_criterion(level):
            continue

        db_row = _find_db_result_for_criterion(db_results, level)
        if not db_row:
            row_changes.append({
                "criteria_level": level,
                "action": "skipped_no_db_row",
            })
            continue

        prev_achieved = bool(db_row.achieved)
        new_achieved = bool(cr.get("achieved"))
        if prev_achieved != new_achieved:
            db_row.achieved = new_achieved  # type: ignore
            if new_achieved and int(db_row.score or 0) < 50:
                db_row.score = max(int(db_row.score or 0), 75)  # type: ignore
            elif not new_achieved and int(db_row.score or 0) >= 75:
                db_row.score = min(int(db_row.score or 0), 40)  # type: ignore

        note = str(cr.get("runtime_observation_note_ar") or "").strip()
        if note:
            existing = str(db_row.feedback or "")
            marker = "[Runtime adjudication]"
            if marker not in existing and note not in existing:
                feedback_text = (
                    f"{existing}\n\n{marker}\n{note}".strip()
                    if existing
                    else f"{marker}\n{note}"
                )
                db_row.feedback = feedback_text  # type: ignore

        row_changes.append({
            "criteria_level": level,
            "action": "updated",
            "achieved_before": prev_achieved,
            "achieved_after": new_achieved,
            "achievement_authority": cr.get("achievement_authority"),
        })

    summary = (
        db.query(GradingSummary)
        .filter(GradingSummary.submission_id == submission.id)
        .first()
    )
    summary_updates: Dict[str, Any] = {}
    if summary:
        if working.get("grade_level"):
            summary.grade_level = str(working["grade_level"])  # type: ignore
            summary_updates["grade_level"] = summary.grade_level
        if working.get("percentage") is not None:
            summary.percentage = float(working["percentage"])  # type: ignore
            summary_updates["percentage"] = summary.percentage
        if working.get("total_score") is not None:
            summary.total_score = int(working["total_score"])  # type: ignore
            summary_updates["total_score"] = summary.total_score

    grading_snapshot.update({
        "criteria_results": working.get("criteria_results"),
        "runtime_criterion_mapping": working.get("runtime_criterion_mapping"),
        "runtime_adjudication": working.get("runtime_adjudication"),
        "runtime_adjudication_db_sync": {
            "applied": True,
            "row_changes": row_changes,
            "summary_updates": summary_updates,
            "require_human_playtest": require_human_playtest,
            "human_playtest_verified": human_ok,
        },
    })
    submission.grading_snapshot_json = json.dumps(  # type: ignore
        grading_snapshot,
        ensure_ascii=False,
    )

    db.commit()

    return {
        "applied": True,
        "changes": row_changes,
        "summary_updates": summary_updates,
        "runtime_adjudication": working.get("runtime_adjudication"),
        "message_ar": (
            "تم تطبيق runtime adjudication على C.P5/C.P6 في قاعدة البيانات — "
            "راجع التقرير قبل تأكيد الدرجة النهائية."
        ),
    }
