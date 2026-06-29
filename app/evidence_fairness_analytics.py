"""
Evidence Fairness Analytics — batch-level evidentiary opportunity analysis.

Read-only analytical overlay — descriptive, not normative.
Uses replay-derived state; never mutates grades, authority, or adjudication.

Vocabulary: imbalance, disparity, evidence sensitivity, procedural concentration.
Never: «unfair».
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from typing import Any, Dict, List, Optional, Set, Tuple

from app.academic_event_replay import build_academic_timeline_replay
from app.authority_transition_replay import build_authority_transition_replay
from app.deterministic_replay_engine import verify_deterministic_replay

FAIRNESS_EPOCH_DEFAULT = "EVIDENCE_FAIRNESS_v1"
METRIC_CONTRACT_DEFAULT = "evidence_distribution_v1"
ANALYTICS_MODE = "evidence_fairness_analytical_overlay"

EVIDENCE_PROFILE_LABELS: Dict[str, Dict[str, str]] = {
    "word_pdf": {
        "label_en": "Word/PDF documentation",
        "label_ar": "توثيق Word/PDF",
    },
    "runtime_only": {
        "label_en": "Runtime-only (exe-led, minimal doc/code)",
        "label_ar": "Runtime-only — exe بدون توثيق/كود كافٍ",
    },
    "partial_code_extraction": {
        "label_en": "Partial code extraction",
        "label_ar": "استخراج كود جزئي",
    },
    "human_playtest_present": {
        "label_en": "Human playtest present",
        "label_ar": "Manual Playtest L5 موجود",
    },
    "documentation_rich": {
        "label_en": "Documentation-rich (doc + testing/screenshots)",
        "label_ar": "توثيق غني (Word + testing/screenshots)",
    },
    "testing_evidence_present": {
        "label_en": "Testing evidence present",
        "label_ar": "أدلة testing موجودة",
    },
    "unclassified": {
        "label_en": "Unclassified evidence profile",
        "label_ar": "ملف أدلة غير مصنّف",
    },
}


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


def _inventory_and_coverage(snap: Dict[str, Any]) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    inv = snap.get("artifact_inventory") or {}
    expl = snap.get("explainability_layer") or {}
    cov = expl.get("extraction_coverage") or inv.get("extraction_coverage") or {}
    return inv, cov


def _has_word_pdf(inv: Dict[str, Any]) -> bool:
    doc = inv.get("documentation") or {}
    return any(
        str(f.get("ext") or "").lower() in (".docx", ".doc", ".pdf", ".odt")
        for f in doc.get("files") or []
    )


def _has_executable(inv: Dict[str, Any]) -> bool:
    exe = inv.get("executable_artifacts") or {}
    rt = inv.get("runtime_artifacts") or {}
    return bool(exe.get("files") or rt.get("executables_detected"))


def _has_source_code(inv: Dict[str, Any]) -> bool:
    src = inv.get("source_code") or {}
    return bool(src.get("files"))


def classify_evidence_profiles(
    snap: Dict[str, Any],
    *,
    replay_state: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Assign one or more evidence profiles — descriptive taxonomy only.
    """
    inv, cov = _inventory_and_coverage(snap)
    replay_state = replay_state or {}
    profiles: List[str] = []

    word = _has_word_pdf(inv)
    exe = _has_executable(inv)
    code = _has_source_code(inv)
    weak = bool(cov.get("weak_analysis_risk"))
    ratio = cov.get("coverage_ratio")
    low_coverage = ratio is not None and float(ratio) < 0.5

    l5 = inv.get("l5_human_playtest") or {}
    playtest = replay_state.get("playtest") or {}
    has_playtest = bool(l5.get("pass")) or bool(
        replay_state.get("playtest_completed") or playtest.get("completed")
    )

    testing = inv.get("testing_evidence") or {}
    emb = inv.get("embedded_screenshots") or {}
    has_testing = bool(testing.get("files"))
    has_screenshots = (emb.get("count") or 0) > 0

    if word:
        profiles.append("word_pdf")
    if exe and not word and (not code or weak or low_coverage):
        profiles.append("runtime_only")
    if weak or low_coverage:
        profiles.append("partial_code_extraction")
    if has_playtest:
        profiles.append("human_playtest_present")
    if word and (has_testing or has_screenshots):
        profiles.append("documentation_rich")
    if has_testing:
        profiles.append("testing_evidence_present")

    if not profiles:
        profiles.append("unclassified")
    return profiles


def _hold_on_execution_criteria(
    snap: Dict[str, Any],
    replay_state: Optional[Dict[str, Any]] = None,
) -> bool:
    lineage = (
        (snap.get("explainability_layer") or {}).get("evidence_lineage")
        or snap.get("evidence_lineage")
        or {}
    )
    for key in ("C.P5", "C.P6"):
        crit = (lineage.get("criteria") or {}).get(key) or {}
        if crit.get("status") == "HOLD":
            return True

    replay_state = replay_state or {}
    for key in ("P5", "P6"):
        crit = (replay_state.get("criteria") or {}).get(key) or {}
        if isinstance(crit, dict) and crit.get("status") == "HOLD":
            return True
    return False


def _authority_escalated(authority_report: Dict[str, Any]) -> bool:
    transitions = authority_report.get("transitions") or []
    if not transitions:
        return False
    for t in transitions:
        fr = str(t.get("from_authority") or "")
        to = str(t.get("to_authority") or "")
        if "SYSTEM" in fr and ("HUMAN" in to or "L4" in to or "L5" in to):
            return True
        if t.get("direction") == "escalation":
            return True
    return len(transitions) > 0


def analyze_submission_evidence_fairness(
    submission,
    *,
    graded_at: Optional[str] = None,
) -> Dict[str, Any]:
    """Single submission — replay-derived evidence fairness row."""
    snap = _load_snapshot(submission)
    sid = getattr(submission, "id", None)
    name = getattr(submission, "student_name", "") or ""

    if not snap or snap.get("success") is False:
        return {"submission_id": sid, "student_name": name, "skipped": True, "reason": "no_snapshot"}

    timeline = build_academic_timeline_replay(snap, graded_at=graded_at)
    events = timeline.get("events") or []
    verification = verify_deterministic_replay(events, snap)
    state = verification.get("state_summary") or {}
    authority = build_authority_transition_replay(snap, events=events)

    profiles = classify_evidence_profiles(snap, replay_state=state)
    inv, cov = _inventory_and_coverage(snap)

    return {
        "submission_id": sid,
        "student_name": name,
        "skipped": False,
        "evidence_profiles": profiles,
        "hold_present": _hold_on_execution_criteria(snap, state),
        "authority_escalated": _authority_escalated(authority),
        "authority_transitions": len(authority.get("transitions") or []),
        "coverage_ratio": cov.get("coverage_ratio"),
        "weak_extraction": bool(cov.get("weak_analysis_risk")),
        "runtime_gated": bool((state.get("governance") or {}).get("runtime_gated")),
        "replay_epoch": verification.get("replay_epoch"),
        "replay_verified": verification.get("replay_verified"),
    }


def _build_matrix_row(
    profile: str,
    stats: Dict[str, Any],
    *,
    batch_total: int,
) -> Dict[str, Any]:
    count = int(stats.get("count") or 0)
    hold_count = int(stats.get("hold_count") or 0)
    escalation_count = int(stats.get("escalation_count") or 0)
    labels = EVIDENCE_PROFILE_LABELS.get(profile, EVIDENCE_PROFILE_LABELS["unclassified"])

    availability = round(count / max(batch_total, 1), 4)
    hold_rate = round(hold_count / max(count, 1), 4)
    escalation_rate = round(escalation_count / max(count, 1), 4)

    return {
        "profile": profile,
        "label_en": labels["label_en"],
        "label_ar": labels["label_ar"],
        "submissions_matched": count,
        "availability_rate": availability,
        "hold_rate": hold_rate,
        "authority_escalation_rate": escalation_rate,
        "avg_coverage_ratio": round(float(stats.get("coverage_sum") or 0) / max(count, 1), 4)
        if count
        else None,
        "weak_extraction_rate": round(
            int(stats.get("weak_count") or 0) / max(count, 1), 4
        ),
        "runtime_gated_rate": round(
            int(stats.get("runtime_gated_count") or 0) / max(count, 1), 4
        ),
    }


def _detect_evidence_sensitivity(
    matrix: List[Dict[str, Any]],
    *,
    batch_hold_rate: float,
) -> List[Dict[str, Any]]:
    """Profiles where HOLD rate materially exceeds batch baseline — descriptive only."""
    zones: List[Dict[str, Any]] = []
    for row in matrix:
        if row["profile"] == "unclassified":
            continue
        hr = float(row.get("hold_rate") or 0)
        delta = round(hr - batch_hold_rate, 4)
        if delta >= 0.25 and row.get("submissions_matched", 0) >= 1:
            zones.append(
                {
                    "profile": row["profile"],
                    "label_ar": row["label_ar"],
                    "hold_rate": hr,
                    "batch_hold_rate": batch_hold_rate,
                    "hold_rate_delta": delta,
                    "sensitivity_class": "elevated" if delta >= 0.4 else "moderate",
                }
            )
    zones.sort(key=lambda z: z["hold_rate_delta"], reverse=True)
    return zones


def _detect_structural_imbalance(matrix: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Availability vs outcome disparity — no normative verdict."""
    imbalances: List[Dict[str, Any]] = []
    hold_rates = [float(r.get("hold_rate") or 0) for r in matrix if r.get("submissions_matched")]
    if not hold_rates:
        return imbalances
    spread = max(hold_rates) - min(hold_rates)
    if spread >= 0.35:
        high = max(matrix, key=lambda r: float(r.get("hold_rate") or 0))
        low = min(
            (r for r in matrix if r.get("submissions_matched")),
            key=lambda r: float(r.get("hold_rate") or 0),
        )
        imbalances.append(
            {
                "type": "hold_rate_disparity",
                "spread": round(spread, 4),
                "highest_profile": high["profile"],
                "highest_hold_rate": high["hold_rate"],
                "lowest_profile": low["profile"],
                "lowest_hold_rate": low["hold_rate"],
                "label_ar": "تفاوت HOLD rate بين profiles أدلة مختلفة",
            }
        )
    avail = [float(r.get("availability_rate") or 0) for r in matrix]
    if avail and max(avail) - min(avail) >= 0.5:
        imbalances.append(
            {
                "type": "availability_disparity",
                "spread": round(max(avail) - min(avail), 4),
                "label_ar": "توزيع غير متوازن لأنواع الأدلة المتاحة عبر الدفعة",
            }
        )
    return imbalances


def build_batch_evidence_fairness_report(
    db,
    batch_id: int,
    *,
    fairness_epoch: str = FAIRNESS_EPOCH_DEFAULT,
    metric_contract: str = METRIC_CONTRACT_DEFAULT,
) -> Dict[str, Any]:
    """
    Batch Evidence Fairness Matrix — evidentiary opportunity analysis.
    Read-only consumer; never mutates submissions.
    """
    from app.models import Submission, SubmissionStatus

    subs = (
        db.query(Submission)
        .filter(Submission.batch_id == batch_id, Submission.status == SubmissionStatus.COMPLETED)
        .all()
    )

    rows: List[Dict[str, Any]] = []
    profile_stats: Dict[str, Dict[str, Any]] = defaultdict(
        lambda: {
            "count": 0,
            "hold_count": 0,
            "escalation_count": 0,
            "coverage_sum": 0.0,
            "weak_count": 0,
            "runtime_gated_count": 0,
        }
    )

    hold_total = 0
    escalation_total = 0

    for sub in subs:
        graded_at = None
        summary = getattr(sub, "summary", None)
        if summary and getattr(summary, "graded_at", None):
            graded_at = summary.graded_at.isoformat() + "Z"
        row = analyze_submission_evidence_fairness(sub, graded_at=graded_at)
        rows.append(row)
        if row.get("skipped"):
            continue

        if row.get("hold_present"):
            hold_total += 1
        if row.get("authority_escalated"):
            escalation_total += 1

        seen: Set[str] = set()
        for profile in row.get("evidence_profiles") or []:
            if profile in seen:
                continue
            seen.add(profile)
            st = profile_stats[profile]
            st["count"] += 1
            if row.get("hold_present"):
                st["hold_count"] += 1
            if row.get("authority_escalated"):
                st["escalation_count"] += 1
            if row.get("coverage_ratio") is not None:
                st["coverage_sum"] += float(row["coverage_ratio"])
            if row.get("weak_extraction"):
                st["weak_count"] += 1
            if row.get("runtime_gated"):
                st["runtime_gated_count"] += 1

    analyzed = [r for r in rows if not r.get("skipped")]
    batch_total = len(analyzed) or 1
    batch_hold_rate = round(hold_total / batch_total, 4)

    matrix = [
        _build_matrix_row(profile, stats, batch_total=batch_total)
        for profile, stats in sorted(
            profile_stats.items(),
            key=lambda kv: (-kv[1]["count"], kv[0]),
        )
    ]

    sensitivity_zones = _detect_evidence_sensitivity(matrix, batch_hold_rate=batch_hold_rate)
    structural_imbalance = _detect_structural_imbalance(matrix)

    report_id = f"efa_{uuid.uuid4().hex[:16]}"
    body = {
        "report_id": report_id,
        "schema": "1.0",
        "mode": ANALYTICS_MODE,
        "batch_id": batch_id,
        "fairness_epoch": fairness_epoch,
        "metric_contract": metric_contract,
        "submissions_total": len(subs),
        "submissions_analyzed": len(analyzed),
        "source": "deterministic_replay_engine",
        "read_only": True,
        "normative_boundary_ar": (
            "وصفي — يصف أنماط disparity وevidence sensitivity — ليس حكم عدالة normative"
        ),
        "normative_boundary_en": (
            "Descriptive — reports disparity patterns and evidence sensitivity — "
            "not a normative fairness verdict"
        ),
        "disclaimer_ar": (
            "تحليل Fairness of Evidentiary Opportunity — read-only overlay. "
            "يستخدم imbalance / disparity / evidence sensitivity — لا يستخدم «unfair»."
        ),
        "disclaimer_en": (
            "Fairness of Evidentiary Opportunity — read-only overlay. "
            "Uses imbalance / disparity / evidence sensitivity — never «unfair»."
        ),
        "batch_summary": {
            "batch_hold_rate": batch_hold_rate,
            "batch_authority_escalation_rate": round(escalation_total / batch_total, 4),
            "weak_extraction_submissions": sum(1 for r in analyzed if r.get("weak_extraction")),
            "runtime_gated_submissions": sum(1 for r in analyzed if r.get("runtime_gated")),
        },
        "evidence_fairness_matrix": matrix,
        "evidence_sensitivity_zones": sensitivity_zones,
        "structural_imbalance": structural_imbalance,
        "procedural_concentration_note_ar": (
            "تركيز HOLD على profiles معينة يُقرأ كـ procedural concentration — "
            "ليس verdict على عدالة السياسة"
        ),
        "rows": rows,
        "report_hash": "",
    }
    hash_body = {k: v for k, v in body.items() if k not in ("report_hash", "rows")}
    body["report_hash"] = hashlib.sha256(_stable_json(hash_body).encode("utf-8")).hexdigest()
    return body
