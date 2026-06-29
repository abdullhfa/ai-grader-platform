"""
Statistical Distribution Layer — batch-level score and achievement distributions.

Read-only analytical overlay — descriptive statistics only.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from statistics import mean, median, pstdev
from typing import Any, Dict, List, Optional

DISTRIBUTION_CONTRACT = "statistical_distribution_v1"
ANALYTICS_MODE = "statistical_distribution_analytical_overlay"


def _stable_json(obj: Any) -> str:
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _load_snapshot(submission) -> Optional[Dict[str, Any]]:
    raw = getattr(submission, "grading_snapshot_json", None)
    if not raw:
        return None
    try:
        data = json.loads(str(raw))
        return data if isinstance(data, dict) else None
    except (json.JSONDecodeError, TypeError):
        return None


def _grade_bucket(grade_level: str) -> str:
    g = (grade_level or "").strip().upper()
    for token in ("DISTINCTION", "D", "MERIT", "M", "PASS", "P", "U"):
        if token in g.split()[0] if g else "":
            return token[0] if token in ("D", "M", "P", "U") else token[:1]
    if g.startswith("D"):
        return "D"
    if g.startswith("M"):
        return "M"
    if g.startswith("P"):
        return "P"
    return "U"


def build_batch_statistical_distribution_report(
    db,
    batch_id: int,
    *,
    distribution_contract: str = DISTRIBUTION_CONTRACT,
) -> Dict[str, Any]:
    from app.models import GradingResult, GradingSummary, Submission

    submissions = (
        db.query(Submission).filter(Submission.batch_id == batch_id).all()
    )
    rows: List[Dict[str, Any]] = []
    criterion_scores: Dict[str, List[int]] = defaultdict(list)
    criterion_achieved: Dict[str, List[bool]] = defaultdict(list)
    grade_counts: Dict[str, int] = defaultdict(int)
    percentages: List[float] = []
    total_scores: List[int] = []

    for sub in submissions:
        snap = _load_snapshot(sub) or {}
        summary = (
            db.query(GradingSummary).filter(GradingSummary.submission_id == sub.id).first()
        )
        grade = (summary.grade_level if summary else None) or snap.get("grade_level") or "U"
        pct = float(summary.percentage if summary and summary.percentage is not None else snap.get("percentage") or 0)
        tscore = int(summary.total_score if summary and summary.total_score is not None else snap.get("total_score") or 0)
        grade_counts[_grade_bucket(str(grade))] += 1
        percentages.append(pct)
        total_scores.append(tscore)

        db_results = (
            db.query(GradingResult).filter(GradingResult.submission_id == sub.id).all()
        )
        for r in db_results:
            crit = r.criteria
            lvl = str(crit.criteria_level if crit else "unknown")
            criterion_scores[lvl].append(int(r.score or 0))
            criterion_achieved[lvl].append(bool(r.achieved))

        rows.append(
            {
                "submission_id": sub.id,
                "student_name": sub.student_name,
                "grade_level": grade,
                "percentage": pct,
                "total_score": tscore,
            }
        )

    n = max(len(submissions), 1)
    per_criterion: List[Dict[str, Any]] = []
    for lvl, scores in sorted(criterion_scores.items()):
        achieved_list = criterion_achieved.get(lvl) or []
        ach_rate = sum(1 for a in achieved_list if a) / max(len(achieved_list), 1)
        per_criterion.append(
            {
                "criteria_level": lvl,
                "count": len(scores),
                "mean_score": round(mean(scores), 2) if scores else 0,
                "median_score": round(median(scores), 2) if scores else 0,
                "stdev_score": round(pstdev(scores), 2) if len(scores) > 1 else 0.0,
                "min_score": min(scores) if scores else 0,
                "max_score": max(scores) if scores else 0,
                "achievement_rate": round(ach_rate * 100, 1),
            }
        )

    report_core = {
        "batch_id": batch_id,
        "submission_count": len(submissions),
        "grade_distribution": dict(grade_counts),
        "percentage": {
            "mean": round(mean(percentages), 2) if percentages else 0,
            "median": round(median(percentages), 2) if percentages else 0,
            "stdev": round(pstdev(percentages), 2) if len(percentages) > 1 else 0.0,
            "min": round(min(percentages), 2) if percentages else 0,
            "max": round(max(percentages), 2) if percentages else 0,
        },
        "total_score": {
            "mean": round(mean(total_scores), 2) if total_scores else 0,
            "median": round(median(total_scores), 2) if total_scores else 0,
        },
        "per_criterion": per_criterion,
        "students": rows,
    }
    digest = hashlib.sha256(_stable_json(report_core).encode()).hexdigest()[:16]

    return {
        "report_id": f"statdist_{batch_id}_{uuid.uuid4().hex[:8]}",
        "report_type": "statistical_distribution_batch",
        "analytics_mode": ANALYTICS_MODE,
        "distribution_contract": distribution_contract,
        "digest": digest,
        **report_core,
        "interpretation_ar": (
            "توزيع إحصائي وصفي فقط — لا يغيّر الدرجات ولا يقيّم عدالة التصحيح."
        ),
    }
