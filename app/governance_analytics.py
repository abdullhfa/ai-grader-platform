"""
Governance Analytics — consumer of deterministic replay (NOT source of truth).

Aggregates replayed state, verification, authority transitions, and governance signals
per batch for institutional oversight.
"""
from __future__ import annotations

import json
from collections import Counter
from typing import Any, Dict, List, Optional

from app.academic_event_replay import build_academic_timeline_replay
from app.authority_transition_replay import build_authority_transition_replay
from app.deterministic_replay_engine import verify_deterministic_replay


def _load_snapshot(submission) -> Optional[Dict[str, Any]]:
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def analyze_submission_governance(submission, *, graded_at: Optional[str] = None) -> Dict[str, Any]:
    """Single submission — replay-derived analytics row."""
    snap = _load_snapshot(submission)
    sid = getattr(submission, "id", None)
    name = getattr(submission, "student_name", "") or ""

    if not snap or snap.get("success") is False:
        return {
            "submission_id": sid,
            "student_name": name,
            "skipped": True,
            "reason": "no_snapshot",
        }

    timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
    events = timeline.get("events") or []
    verification = verify_deterministic_replay(events, snap)
    authority = build_authority_transition_replay(snap, events=events)

    state = verification.get("state_summary") or {}
    gov = state.get("governance") or {}
    hold_reasons: List[str] = []

    lineage = (
        (snap.get("explainability_layer") or {}).get("evidence_lineage")
        or snap.get("evidence_lineage")
        or {}
    )
    for key in ("C.P5", "C.P6"):
        crit = (lineage.get("criteria") or {}).get(key) or {}
        if crit.get("status") == "HOLD":
            hold_reasons.append(f"{key}:HOLD")

    if gov.get("runtime_gated"):
        hold_reasons.append("runtime_gated")
    cov = (snap.get("explainability_layer") or {}).get("extraction_coverage") or (
        (snap.get("artifact_inventory") or {}).get("extraction_coverage") or {}
    )
    weak_extraction = bool(cov.get("weak_analysis_risk"))

    transitions = authority.get("transitions") or []
    system_to_human = sum(
        1
        for t in transitions
        if t.get("from_authority") == "SYSTEM_GOVERNED"
        and "HUMAN" in str(t.get("to_authority") or "")
    )

    return {
        "submission_id": sid,
        "student_name": name,
        "skipped": False,
        "grade_level": state.get("grade_level"),
        "replay_epoch": verification.get("replay_epoch"),
        "replay_verified": verification.get("replay_verified"),
        "protected_digest_match": verification.get("protected_digest_match"),
        "semantic_replay_verified": verification.get("semantic_replay_verified"),
        "authority_match": verification.get("authority_match"),
        "lineage_match": verification.get("lineage_match"),
        "governance_match": verification.get("governance_match"),
        "runtime_gated": bool(gov.get("runtime_gated")),
        "hold_reasons": hold_reasons,
        "weak_extraction": weak_extraction,
        "coverage_ratio": cov.get("coverage_ratio"),
        "authority_transitions": len(transitions),
        "system_to_human_transitions": system_to_human,
        "playtest_completed": state.get("playtest_completed"),
        "event_count": len(events),
        "event_source": timeline.get("source"),
    }


def build_batch_governance_analytics(db, batch_id: int) -> Dict[str, Any]:
    """
    Batch-level governance analytics — all metrics from replay verification.
    Consumer only; never mutates grades or snapshots.
    """
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )

    rows: List[Dict[str, Any]] = []
    hold_counter: Counter[str] = Counter()
    epoch_counter: Counter[str] = Counter()
    verification_failures = 0
    semantic_failures = 0
    runtime_gated_count = 0
    weak_extraction_count = 0
    authority_transition_total = 0
    system_to_human_total = 0
    playtest_completed_count = 0

    for sub in subs:
        graded_at = None
        summary = getattr(sub, "summary", None)
        if summary and getattr(summary, "graded_at", None):
            graded_at = summary.graded_at.isoformat() + "Z"
        row = analyze_submission_governance(sub, graded_at=graded_at)
        rows.append(row)
        if row.get("skipped"):
            continue

        for hr in row.get("hold_reasons") or []:
            hold_counter[hr] += 1
        epoch_counter[str(row.get("replay_epoch") or "unknown")] += 1

        if not row.get("protected_digest_match"):
            verification_failures += 1
        if not row.get("semantic_replay_verified"):
            semantic_failures += 1
        if row.get("runtime_gated"):
            runtime_gated_count += 1
        if row.get("weak_extraction"):
            weak_extraction_count += 1
        authority_transition_total += int(row.get("authority_transitions") or 0)
        system_to_human_total += int(row.get("system_to_human_transitions") or 0)
        if row.get("playtest_completed"):
            playtest_completed_count += 1

    analyzed = [r for r in rows if not r.get("skipped")]
    total = len(analyzed)

    return {
        "schema": "1.0",
        "mode": "governance_analytics_consumer",
        "batch_id": batch_id,
        "submissions_total": len(subs),
        "submissions_analyzed": total,
        "source": "deterministic_replay_engine",
        "note_ar": (
            "تحليل حوكمة — consumer فقط لـ replay verified state. "
            "ليس مصدر الحقيقة."
        ),
        "summary": {
            "replay_verification_failures": verification_failures,
            "semantic_replay_failures": semantic_failures,
            "runtime_gated_rate": round(runtime_gated_count / total, 4) if total else 0.0,
            "weak_extraction_rate": round(weak_extraction_count / total, 4) if total else 0.0,
            "authority_transition_total": authority_transition_total,
            "system_to_human_transitions": system_to_human_total,
            "playtest_completed_count": playtest_completed_count,
            "hold_reasons_top": [
                {"reason": k, "count": v}
                for k, v in hold_counter.most_common(8)
            ],
            "replay_epochs": [
                {"epoch": k, "count": v}
                for k, v in epoch_counter.most_common()
            ],
        },
        "rows": rows,
    }
