"""
Procedural Fairness Analytics — replay-derived procedural observability.

Read-only analytical overlay — journey toward outcome, not outcome alone.
Uses canonical event stream + authority transition semantics.

Vocabulary: concentration, divergence, escalation dependency, procedural asymmetry.
Never: bias, discrimination, unfair.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.academic_event_replay import build_academic_timeline_replay
from app.authority_transition_replay import build_authority_transition_replay
from app.deterministic_replay_engine import verify_deterministic_replay
from app.evidence_fairness_analytics import classify_evidence_profiles

PROCEDURAL_EPOCH_DEFAULT = "PROCEDURAL_ANALYTICS_v1"
METRIC_CONTRACT_DEFAULT = "procedural_flow_v1"
ANALYTICS_MODE = "procedural_fairness_analytical_overlay"

ARCHETYPE_LABELS: Dict[str, Dict[str, str]] = {
    "direct_adjudication": {
        "label_en": "Direct adjudication",
        "label_ar": "Direct adjudication — SYSTEM → final",
    },
    "governance_gated": {
        "label_en": "Governance gated",
        "label_ar": "Governance gated — HOLD → HUMAN",
    },
    "replay_unstable": {
        "label_en": "Replay unstable",
        "label_ar": "Replay unstable — reconstruction-heavy",
    },
    "evidence_sparse": {
        "label_en": "Evidence sparse",
        "label_ar": "Evidence sparse — escalation-dominant",
    },
}

LATENCY_BUCKET_DEFS: List[Tuple[str, float, Optional[float], str]] = [
    ("under_1h", 0, 1, "أقل من ساعة"),
    ("same_day", 1, 24, "نفس اليوم (1–24 ساعة)"),
    ("delayed_1_3d", 24, 72, "1–3 أيام"),
    ("prolonged", 72, None, "أكثر من 3 أيام"),
]


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


def _parse_ts(ts: Optional[str]) -> Optional[datetime]:
    if not ts:
        return None
    s = str(ts).strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def _hours_between(start: Optional[datetime], end: Optional[datetime]) -> Optional[float]:
    if not start or not end:
        return None
    delta = end - start
    return round(max(delta.total_seconds(), 0) / 3600.0, 4)


def _resolve_governance_contract(snap: Dict[str, Any]) -> str:
    rev = snap.get("explainability_revision") or {}
    policy = rev.get("policy_version") or rev.get("governance_contract")
    if policy:
        return str(policy)
    layer = snap.get("explainability_layer") or {}
    gi = layer.get("governance_intent") or (snap.get("artifact_inventory") or {}).get(
        "governance_intent"
    ) or {}
    if gi.get("policy_version"):
        return str(gi["policy_version"])
    obs = (snap.get("artifact_inventory") or {}).get("runtime_observation_report") or {}
    reason = str(obs.get("reason") or "")
    if "FREEZE_v1" in reason or "GOVERNANCE_FREEZE_v1" in reason:
        return "2.1"
    return "2.1"


def _hold_present_in_snapshot(snap: Dict[str, Any], state: Dict[str, Any]) -> bool:
    lineage = (
        (snap.get("explainability_layer") or {}).get("evidence_lineage")
        or snap.get("evidence_lineage")
        or {}
    )
    for key in ("C.P5", "C.P6"):
        crit = (lineage.get("criteria") or {}).get(key) or {}
        if crit.get("status") == "HOLD":
            return True
    for key in ("P5", "P6"):
        crit = (state.get("criteria") or {}).get(key) or {}
        if isinstance(crit, dict) and crit.get("status") == "HOLD":
            return True
    return False


def _latency_bucket(hours: Optional[float]) -> str:
    if hours is None:
        return "unknown"
    for code, lo, hi, _ in LATENCY_BUCKET_DEFS:
        if hi is None and hours >= lo:
            return code
        if hi is not None and lo <= hours < hi:
            return code
    return "prolonged"


def extract_procedural_path(
    events: List[Dict[str, Any]],
    *,
    timeline_source: str,
    snap: Dict[str, Any],
    replay_state: Dict[str, Any],
    authority_report: Dict[str, Any],
    verification: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Procedural path extraction from event timeline — replay-derived only.
    """
    sorted_events = sorted(events, key=lambda e: (e.get("event_seq") or 0, str(e.get("timestamp") or "")))
    transitions = authority_report.get("transitions") or []

    initial_ts = None
    hold_start_ts = None
    hold_end_ts = None
    first_escalation_ts = None
    replay_revision_count = 0
    runtime_gated_seen = False
    human_playtest_seen = False

    for ev in sorted_events:
        et = ev.get("event_type")
        ts = _parse_ts(ev.get("timestamp"))
        if et == "initial_grading" and initial_ts is None:
            initial_ts = ts
        if et == "runtime_gated":
            runtime_gated_seen = True
            if hold_start_ts is None:
                hold_start_ts = ts
        if et == "explainability_revision":
            replay_revision_count += 1
        if et == "human_playtest_completed":
            human_playtest_seen = True
            if hold_end_ts is None:
                hold_end_ts = ts
        if et in ("runtime_adjudication_applied", "authority_transition"):
            payload = ev.get("payload") or {}
            impact = payload if et == "authority_transition" else {}
            status_after = impact.get("status_after") or payload.get("status_after")
            if status_after == "HOLD" and hold_start_ts is None:
                hold_start_ts = ts
            if status_after in ("ACHIEVED", "NOT_ACHIEVED") and hold_end_ts is None:
                hold_end_ts = ts

    escalations = [t for t in transitions if t.get("escalation")]
    for tr in escalations:
        ts = _parse_ts(tr.get("timestamp"))
        if ts and first_escalation_ts is None:
            first_escalation_ts = ts

    last_ts = _parse_ts(sorted_events[-1].get("timestamp")) if sorted_events else None
    hold_present = _hold_present_in_snapshot(snap, replay_state)
    still_in_hold = hold_present and not human_playtest_seen and hold_end_ts is None

    if hold_start_ts and still_in_hold and last_ts:
        hold_end_for_duration = last_ts
    elif hold_start_ts and hold_end_ts:
        hold_end_for_duration = hold_end_ts
    else:
        hold_end_for_duration = None

    hold_duration_hours = _hours_between(hold_start_ts, hold_end_for_duration)
    first_escalation_latency_hours = _hours_between(initial_ts, first_escalation_ts)

    transition_latencies: List[float] = []
    prev_ts = initial_ts
    for tr in transitions:
        ts = _parse_ts(tr.get("timestamp"))
        if prev_ts and ts:
            h = _hours_between(prev_ts, ts)
            if h is not None:
                transition_latencies.append(h)
        if ts:
            prev_ts = ts

    synthetic_count = sum(1 for e in sorted_events if e.get("synthetic"))
    synthetic_ratio = round(synthetic_count / max(len(sorted_events), 1), 4)

    replay_unstable = (
        timeline_source == "synthetic_reconstruction"
        or not verification.get("protected_digest_match", True)
        or not verification.get("semantic_replay_verified", True)
        or replay_revision_count >= 2
    )

    governance_gate_persistent = runtime_gated_seen and still_in_hold

    return {
        "event_count": len(sorted_events),
        "timeline_source": timeline_source,
        "hold_present": hold_present,
        "still_in_hold": still_in_hold,
        "hold_duration_hours": hold_duration_hours,
        "hold_duration_days": round(hold_duration_hours / 24.0, 2)
        if hold_duration_hours is not None
        else None,
        "human_escalated": bool(escalations),
        "escalation_count": len(escalations),
        "first_escalation_latency_hours": first_escalation_latency_hours,
        "authority_transition_latencies_hours": transition_latencies,
        "authority_transition_count": len(transitions),
        "repeated_transitions": len(transitions) >= 3,
        "governance_gate_persistent": governance_gate_persistent,
        "runtime_gated": runtime_gated_seen,
        "replay_revision_count": replay_revision_count,
        "synthetic_event_ratio": synthetic_ratio,
        "replay_verification_mismatch": not verification.get("protected_digest_match", True),
        "replay_unstable": replay_unstable,
        "replay_source_synthetic": timeline_source == "synthetic_reconstruction",
    }


def classify_procedural_archetype(
    path: Dict[str, Any],
    evidence_profiles: List[str],
) -> str:
    if path.get("replay_unstable"):
        return "replay_unstable"
    sparse_profiles = {"partial_code_extraction", "runtime_only"}
    if sparse_profiles.intersection(evidence_profiles) and path.get("human_escalated"):
        return "evidence_sparse"
    if path.get("governance_gate_persistent") or (
        path.get("hold_present") and path.get("human_escalated")
    ):
        return "governance_gated"
    if path.get("runtime_gated") or path.get("human_escalated"):
        return "governance_gated"
    return "direct_adjudication"


def analyze_submission_procedural_fairness(
    submission,
    *,
    graded_at: Optional[str] = None,
) -> Dict[str, Any]:
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

    path = extract_procedural_path(
        events,
        timeline_source=str(timeline.get("source") or "unknown"),
        snap=snap,
        replay_state=state,
        authority_report=authority,
        verification=verification,
    )
    profiles = classify_evidence_profiles(snap, replay_state=state)
    archetype = classify_procedural_archetype(path, profiles)

    return {
        "submission_id": sid,
        "student_name": name,
        "skipped": False,
        "evidence_profiles": profiles,
        "procedural_archetype": archetype,
        "procedural_path": path,
        "replay_epoch": verification.get("replay_epoch"),
        "governance_contract": _resolve_governance_contract(snap),
    }


def _aggregate_profile_procedural(
    profile_stats: Dict[str, Dict[str, Any]],
    profile: str,
    row: Dict[str, Any],
    path: Dict[str, Any],
) -> None:
    st = profile_stats[profile]
    st["count"] += 1
    if path.get("hold_present"):
        st["hold_count"] += 1
    if path.get("hold_duration_hours") is not None:
        st["hold_hours_sum"] += float(path["hold_duration_hours"])
        st["hold_duration_samples"] += 1
    if path.get("human_escalated"):
        st["escalation_count"] += 1
    if path.get("replay_unstable"):
        st["replay_unstable_count"] += 1
    if path.get("replay_source_synthetic"):
        st["synthetic_reconstruction_count"] += 1
    if path.get("governance_gate_persistent"):
        st["gate_persistent_count"] += 1
    if path.get("first_escalation_latency_hours") is not None:
        st["escalation_latency_sum"] += float(path["first_escalation_latency_hours"])
        st["escalation_latency_samples"] += 1


def _build_profile_row(profile: str, stats: Dict[str, Any]) -> Dict[str, Any]:
    count = int(stats.get("count") or 0)
    hold_samples = int(stats.get("hold_duration_samples") or 0)
    esc_samples = int(stats.get("escalation_latency_samples") or 0)
    return {
        "profile": profile,
        "submissions_matched": count,
        "avg_hold_duration_days": round(
            (float(stats.get("hold_hours_sum") or 0) / hold_samples) / 24.0, 2
        )
        if hold_samples
        else None,
        "hold_concentration_rate": round(int(stats.get("hold_count") or 0) / max(count, 1), 4),
        "human_escalation_dependency_rate": round(
            int(stats.get("escalation_count") or 0) / max(count, 1), 4
        ),
        "replay_unstable_concentration_rate": round(
            int(stats.get("replay_unstable_count") or 0) / max(count, 1), 4
        ),
        "synthetic_reconstruction_concentration_rate": round(
            int(stats.get("synthetic_reconstruction_count") or 0) / max(count, 1), 4
        ),
        "governance_gate_persistence_rate": round(
            int(stats.get("gate_persistent_count") or 0) / max(count, 1), 4
        ),
        "avg_escalation_latency_hours": round(
            float(stats.get("escalation_latency_sum") or 0) / esc_samples, 2
        )
        if esc_samples
        else None,
    }


def _build_latency_histogram(latencies: List[float]) -> List[Dict[str, Any]]:
    buckets: Dict[str, int] = defaultdict(int)
    for h in latencies:
        buckets[_latency_bucket(h)] += 1
    out: List[Dict[str, Any]] = []
    for code, _, _, label_ar in LATENCY_BUCKET_DEFS:
        if buckets.get(code):
            out.append({"bucket": code, "label_ar": label_ar, "count": buckets[code]})
    if buckets.get("unknown"):
        out.append({"bucket": "unknown", "label_ar": "غير محدد", "count": buckets["unknown"]})
    return out


def _detect_procedural_bottlenecks(
    profile_rows: List[Dict[str, Any]],
    *,
    batch_escalation_rate: float,
) -> List[Dict[str, Any]]:
    bottlenecks: List[Dict[str, Any]] = []
    for row in profile_rows:
        profile = row["profile"]
        if profile == "unclassified":
            continue
        esc_rate = float(row.get("human_escalation_dependency_rate") or 0)
        if esc_rate >= 0.5 and esc_rate >= batch_escalation_rate + 0.2:
            severity = "high" if esc_rate >= 0.7 else "moderate"
            bottlenecks.append(
                {
                    "bottleneck_type": "HUMAN_ESCALATION_CONCENTRATION",
                    "affected_profile": profile,
                    "severity": severity,
                    "concentration_rate": esc_rate,
                    "batch_escalation_rate": batch_escalation_rate,
                    "label_ar": f"تركيز escalation dependency على {profile}",
                }
            )
        replay_rate = float(row.get("replay_unstable_concentration_rate") or 0)
        if replay_rate >= 0.4:
            bottlenecks.append(
                {
                    "bottleneck_type": "REPLAY_STABILITY_CONCENTRATION",
                    "affected_profile": profile,
                    "severity": "moderate" if replay_rate < 0.7 else "high",
                    "concentration_rate": replay_rate,
                    "label_ar": f"تركيز replay instability على {profile}",
                }
            )
        gate_rate = float(row.get("governance_gate_persistence_rate") or 0)
        if gate_rate >= 0.4:
            bottlenecks.append(
                {
                    "bottleneck_type": "GOVERNANCE_GATE_PERSISTENCE",
                    "affected_profile": profile,
                    "severity": "moderate",
                    "concentration_rate": gate_rate,
                    "label_ar": f"استمرار governance gate على {profile}",
                }
            )
    return bottlenecks


def build_batch_procedural_fairness_report(
    db,
    batch_id: int,
    *,
    procedural_epoch: str = PROCEDURAL_EPOCH_DEFAULT,
    metric_contract: str = METRIC_CONTRACT_DEFAULT,
) -> Dict[str, Any]:
    """Batch procedural fairness — replay-derived procedural observability."""
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
            "hold_hours_sum": 0.0,
            "hold_duration_samples": 0,
            "escalation_count": 0,
            "replay_unstable_count": 0,
            "synthetic_reconstruction_count": 0,
            "gate_persistent_count": 0,
            "escalation_latency_sum": 0.0,
            "escalation_latency_samples": 0,
        }
    )
    archetype_counter: Dict[str, int] = defaultdict(int)
    all_escalation_latencies: List[float] = []
    all_transition_latencies: List[float] = []
    escalation_total = 0
    hold_total = 0
    replay_unstable_total = 0
    synthetic_total = 0
    gate_persistent_total = 0

    for sub in subs:
        graded_at = None
        summary = getattr(sub, "summary", None)
        if summary and getattr(summary, "graded_at", None):
            graded_at = summary.graded_at.isoformat() + "Z"
        row = analyze_submission_procedural_fairness(sub, graded_at=graded_at)
        rows.append(row)
        if row.get("skipped"):
            continue

        path = row.get("procedural_path") or {}
        archetype_counter[row.get("procedural_archetype") or "direct_adjudication"] += 1

        if path.get("hold_present"):
            hold_total += 1
        if path.get("human_escalated"):
            escalation_total += 1
        if path.get("replay_unstable"):
            replay_unstable_total += 1
        if path.get("replay_source_synthetic"):
            synthetic_total += 1
        if path.get("governance_gate_persistent"):
            gate_persistent_total += 1

        if path.get("first_escalation_latency_hours") is not None:
            all_escalation_latencies.append(float(path["first_escalation_latency_hours"]))
        for h in path.get("authority_transition_latencies_hours") or []:
            all_transition_latencies.append(float(h))

        seen_profiles: set[str] = set()
        for profile in row.get("evidence_profiles") or []:
            if profile in seen_profiles:
                continue
            seen_profiles.add(profile)
            _aggregate_profile_procedural(profile_stats, profile, row, path)

    analyzed = [r for r in rows if not r.get("skipped")]
    batch_total = len(analyzed) or 1
    batch_escalation_rate = round(escalation_total / batch_total, 4)

    profile_rows = [
        _build_profile_row(profile, stats)
        for profile, stats in sorted(profile_stats.items(), key=lambda kv: (-kv[1]["count"], kv[0]))
    ]

    bottlenecks = _detect_procedural_bottlenecks(
        profile_rows, batch_escalation_rate=batch_escalation_rate
    )

    archetype_distribution = [
        {
            "archetype": k,
            "label_ar": ARCHETYPE_LABELS.get(k, {}).get("label_ar", k),
            "count": v,
            "rate": round(v / batch_total, 4),
        }
        for k, v in sorted(archetype_counter.items(), key=lambda kv: -kv[1])
    ]

    report_id = f"pfa_{uuid.uuid4().hex[:16]}"
    body = {
        "report_id": report_id,
        "schema": "1.0",
        "mode": ANALYTICS_MODE,
        "batch_id": batch_id,
        "procedural_epoch": procedural_epoch,
        "metric_contract": metric_contract,
        "governance_contract_ref": "2.1",
        "submissions_total": len(subs),
        "submissions_analyzed": len(analyzed),
        "source": "academic_event_log_replay",
        "read_only": True,
        "normative_boundary_ar": (
            "وصفي — procedural observability — concentration / divergence / "
            "escalation dependency — ليس normative audit"
        ),
        "normative_boundary_en": (
            "Descriptive procedural observability — not normative institutional audit"
        ),
        "disclaimer_ar": (
            "Procedural Fairness Analytics — replay-derived journey analysis. "
            "يستخدم concentration / procedural asymmetry — لا bias / discrimination / unfair."
        ),
        "batch_summary": {
            "hold_concentration_rate": round(hold_total / batch_total, 4),
            "human_escalation_dependency_rate": batch_escalation_rate,
            "replay_unstable_concentration_rate": round(replay_unstable_total / batch_total, 4),
            "synthetic_reconstruction_concentration_rate": round(synthetic_total / batch_total, 4),
            "governance_gate_persistence_rate": round(gate_persistent_total / batch_total, 4),
            "avg_hold_duration_days": round(
                sum(
                    float((r.get("procedural_path") or {}).get("hold_duration_hours") or 0)
                    for r in analyzed
                    if (r.get("procedural_path") or {}).get("hold_duration_hours") is not None
                )
                / max(
                    sum(
                        1
                        for r in analyzed
                        if (r.get("procedural_path") or {}).get("hold_duration_hours") is not None
                    ),
                    1,
                )
                / 24.0,
                2,
            ),
        },
        "procedural_flow_by_profile": profile_rows,
        "authority_transition_latency_histogram": _build_latency_histogram(all_transition_latencies),
        "escalation_latency_histogram": _build_latency_histogram(all_escalation_latencies),
        "procedural_archetype_distribution": archetype_distribution,
        "procedural_bottlenecks": bottlenecks,
        "procedural_asymmetry_note_ar": (
            "اختلاف مسارات procedural بين profiles — divergence وصفي — "
            "ليس verdict على عدالة مؤسسية"
        ),
        "rows": rows,
        "report_hash": "",
    }
    hash_body = {k: v for k, v in body.items() if k not in ("report_hash", "rows")}
    body["report_hash"] = hashlib.sha256(_stable_json(hash_body).encode("utf-8")).hexdigest()
    return body
