"""
Governance Pilot Observatory — human behaviour observation (not grading).

Worksheet prefill (Section A from snapshot) + manual Sections B–E + cohort synthesis.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.facilitator_epistemic_worksheet import (
    build_section_e_template,
    empty_section_e,
    synthesize_epistemic_behavioural_evidence,
)
from app.epistemic_trace_capture import (
    append_epistemic_trace,
    empty_epistemic_trace,
    enrich_trace_advisory,
    normalize_epistemic_trace,
)

WORKSHOP_DIR = Path("app/calibration/human_cohort_workshop")
OBSERVATIONS_FILE = "observations.jsonl"
INCIDENTS_FILE = "incidents.jsonl"
WORKSHEET_VERSION = "GOVERNANCE_PILOT_WORKSHEET_v1.1"

# Manual GFM → default severity for Section C quick-pick
WORKSHOP_EVENT_SEVERITY: Dict[str, str] = {
    "GFM_MODALITY_DOMINANCE": "S3",
    "GFM_AUTHORITY_INFLATION": "S4",
    "GFM_REPLAY_INCOMPLETENESS": "S2",
    "GFM_REVIEWER_AUTHORITY_CONFUSION": "S4",
    "GFM_TRUST_EROSION": "S4",
    "GFM_CONTRADICTION_INVISIBILITY": "S3",
    "GFM_DRIFT_SILENCE": "S5",
    "GFM_BOUNDARY_OMISSION": "S3",
    "GFM_FALSE_CORROBORATION": "S3",
    "GFM_SEMANTIC_ESCALATION": "S3",
    "GFM_CANONICAL_DRIFT": "S4",
    "replay_omission": "S2",
}


def _ensure_workshop_dir() -> Path:
    WORKSHOP_DIR.mkdir(parents=True, exist_ok=True)
    return WORKSHOP_DIR


def _read_jsonl(path: Path) -> List[Dict[str, Any]]:
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def extract_runtime_evidence_state(snapshot: Dict[str, Any]) -> Dict[str, Any]:
    """Section A — auto-prefill from grading snapshot (system state, not human)."""
    inv = snapshot.get("artifact_inventory") or {}
    rt = inv.get("runtime_evidence_level") or {}
    level = rt.get("level", 0)
    exe = inv.get("executable_artifacts") or {}
    videos = inv.get("video_artifacts") or inv.get("gameplay_videos") or {}
    cross = inv.get("cross_artifact_consistency") or {}
    temporal = inv.get("temporal_consistency") or {}

    contradiction_flags: List[str] = []
    for amb in cross.get("ambiguities") or []:
        code = amb.get("code") or amb.get("signal") or str(amb)
        contradiction_flags.append(str(code))
    for sig in temporal.get("temporal_consistency_signals") or []:
        code = sig.get("code") or sig.get("signal") or str(sig)
        contradiction_flags.append(str(code))

    has_video = bool(
        videos.get("files")
        or inv.get("has_gameplay_video")
        or inv.get("has_video_artifacts")
    )
    has_exe = bool(
        inv.get("has_executable_artifacts")
        or exe.get("files")
    )

    return {
        "runtime_level": f"L{level}",
        "runtime_level_numeric": int(level or 0),
        "executable_detected": has_exe,
        "executable_files_sample": [
            f.get("name") or f.get("path") or str(f)
            for f in (exe.get("files") or [])[:5]
        ],
        "gameplay_video": has_video,
        "runtime_verified": level >= 5,
        "contradiction_flags": contradiction_flags[:8],
        "authority_ceiling": rt.get("authority_ceiling") or rt.get("label"),
        "replay_available": bool(snapshot.get("authority_replay")),
        "prefill_source": "grading_snapshot",
    }


def build_worksheet_draft(
    *,
    submission_id: int,
    student_name: str = "",
    batch_id: Optional[int] = None,
    snapshot: Optional[Dict[str, Any]] = None,
    drift: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Full worksheet template with Section A prefilled; B–D empty for human."""
    snap = snapshot or {}
    section_a = extract_runtime_evidence_state(snap) if snap else {}

    suggested_events: List[Dict[str, str]] = []
    for sig in (drift or {}).get("drift_signals") or []:
        gfm = sig.get("failure_mode_id")
        if gfm:
            suggested_events.append({
                "event": gfm,
                "severity": WORKSHOP_EVENT_SEVERITY.get(gfm, "S3"),
                "source": "drift_monitor",
            })
    if section_a.get("replay_available") is False and snap:
        suggested_events.append({
            "event": "replay_omission",
            "severity": "S2",
            "source": "system_hint",
        })

    replay_gate = {
        "required": True,
        "workflow": "replay_first",
        "instruction_ar": (
            "يجب فتح Authority Replay قبل Sections B–E. "
            "كل contradiction و authority ceiling يجب أن يظهر في replay."
        ),
        "replay_url": f"/authority-replay/{submission_id}",
        "sections_locked_until_replay": ["section_b_reviewer_behaviour", "section_c_governance_events", "section_d_trust_signals", "section_e_epistemic_behaviour"],
    }

    return {
        "worksheet_version": WORKSHEET_VERSION,
        "submission_id": submission_id,
        "student_name": student_name,
        "batch_id": batch_id,
        "cohort_id": f"batch_{batch_id}" if batch_id else None,
        "replay_first_gate": replay_gate,
        "section_a_runtime_evidence_state": section_a,
        "section_b_reviewer_behaviour": {
            "l3_interpreted_as_verification": None,
            "replay_opened": None,
            "downgrade_accepted": None,
            "authority_boundary_overridden": None,
            "hold_considered": None,
            "hold_applied": None,
            "notes_ar": "",
        },
        "section_c_governance_events": suggested_events,
        "section_d_trust_signals": {
            "reviewer_confidence": None,
            "trust_retained_after_disagreement": None,
            "ambiguity_understandable": None,
        },
        "section_e_epistemic_behaviour": empty_section_e(),
        "section_e_meta": build_section_e_template(),
        "section_f_epistemic_trace": empty_epistemic_trace(section_a=section_a),
        "epistemic_trace_capture_enabled": True,
        "drift_status": (drift or {}).get("status"),
        "drift_summary_ar": (drift or {}).get("summary_ar"),
        "authority_replay_url": f"/authority-replay/{submission_id}",
    }


def validate_replay_first(record: Dict[str, Any]) -> Dict[str, Any]:
    """Replay-first gate — facilitator must consult replay before saving worksheet."""
    sec_b = record.get("section_b_reviewer_behaviour") or {}
    replay_opened = sec_b.get("replay_opened")
    replay_consulted_at = record.get("replay_consulted_at") or sec_b.get("replay_consulted_at")
    if replay_opened is True or replay_consulted_at:
        return {"ok": True}
    return {
        "ok": False,
        "code": "replay_first_required",
        "message_ar": (
            "يجب فتح Authority Replay وتأكيد replay_opened=true قبل حفظ ورقة المراقبة. "
            "Workflow: replay → contradictions → authority ceiling → Sections B–E."
        ),
        "replay_url": record.get("authority_replay_url"),
    }


def validate_section_e_before_d(record: Dict[str, Any]) -> Dict[str, Any]:
    """Phase 2 — epistemic behaviour precedes trust sentiment."""
    from app.facilitator_epistemic_worksheet import EPISTEMIC_QUESTIONS

    sec_e = record.get("section_e_epistemic_behaviour") or {}
    answers = sec_e.get("answers") or {}
    missing = [
        q["id"] for q in EPISTEMIC_QUESTIONS
        if not answers.get(q["id"])
    ]
    if missing or not sec_e.get("authority_boundaries_preserved"):
        sec_d = record.get("section_d_trust_signals") or {}
        has_d = any(
            sec_d.get(k) is not None
            for k in ("reviewer_confidence", "trust_retained_after_disagreement", "ambiguity_understandable")
        )
        if has_d:
            return {
                "ok": False,
                "code": "section_e_before_d",
                "message_ar": (
                    "Phase 2: أكمل Section E (كل الأسئلة + authority boundaries) "
                    "قبل Section D — epistemic behaviour precedes trust sentiment."
                ),
                "missing_epistemic_questions": missing,
            }
    return {"ok": True}


def save_observation(record: Dict[str, Any]) -> Dict[str, Any]:
    """Persist completed governance observation worksheet."""
    gate = validate_replay_first(record)
    if not gate.get("ok"):
        return {**gate, "saved": False}

    phase2: Dict[str, Any] = {"registered": False}
    batch_id = record.get("batch_id")
    if batch_id is not None:
        from app.phase2_institutional_observation import get_phase2_cohort_state

        phase2 = get_phase2_cohort_state(int(batch_id))
        if phase2.get("registered") and phase2.get("status") == "observation_active":
            e_gate = validate_section_e_before_d(record)
            if not e_gate.get("ok"):
                return {**e_gate, "saved": False}
            record["phase2_mode"] = "observe_only"
            record["phase2_id"] = phase2.get("phase")

    if (
        phase2.get("registered")
        and phase2.get("status") == "cooling_period"
        and phase2.get("cooling_period_active")
    ):
        return {
            "ok": False,
            "code": "cooling_period_active",
            "message_ar": "cooling period — لا observations جديدة ولا governance edits.",
            "saved": False,
        }
    _ensure_workshop_dir()
    path = WORKSHOP_DIR / OBSERVATIONS_FILE
    now = datetime.datetime.utcnow().isoformat() + "Z"
    out = {
        **record,
        "worksheet_version": record.get("worksheet_version") or WORKSHEET_VERSION,
        "logged_at": now,
        "source": "governance_pilot_observatory",
    }
    sec_a_hint = record.get("section_a_runtime_evidence_state") or {}
    trace_raw = record.get("section_f_epistemic_trace")
    if trace_raw is not None:
        normalized_trace = normalize_epistemic_trace(
            trace_raw,
            section_a=sec_a_hint,
            replay_consulted_at=out.get("replay_consulted_at"),
        )
        enrich_trace_advisory(normalized_trace, out)
        out["section_f_epistemic_trace"] = normalized_trace
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(out, ensure_ascii=False) + "\n")
    trace_id = append_epistemic_trace(out) if out.get("section_f_epistemic_trace") else None
    return {"ok": True, "log_path": str(path), "logged_at": now, "trace_id": trace_id}


def load_observations(
    *,
    batch_id: Optional[int] = None,
    submission_id: Optional[int] = None,
) -> List[Dict[str, Any]]:
    rows = _read_jsonl(WORKSHOP_DIR / OBSERVATIONS_FILE)
    if batch_id is not None:
        rows = [
            r for r in rows
            if r.get("batch_id") == batch_id
            or r.get("cohort_id") == f"batch_{batch_id}"
        ]
    if submission_id is not None:
        rows = [r for r in rows if r.get("submission_id") == submission_id]
    return rows


def load_incidents(batch_id: Optional[int] = None) -> List[Dict[str, Any]]:
    rows = _read_jsonl(WORKSHOP_DIR / INCIDENTS_FILE)
    if batch_id is None:
        return rows
    # Incidents may not have batch_id; keep all for synthesis + filter by submission if needed
    return rows


def _avg(values: List[float]) -> Optional[float]:
    if not values:
        return None
    return round(sum(values) / len(values), 2)


def _categorize_pilot_submission(snapshot: Dict[str, Any]) -> List[str]:
    """Tag submission for balanced pilot pool selection."""
    inv = snapshot.get("artifact_inventory") or {}
    tags: List[str] = []
    has_exe = bool(inv.get("has_executable_artifacts"))
    videos = inv.get("video_artifacts") or inv.get("gameplay_videos") or {}
    has_video = bool(
        videos.get("files")
        or inv.get("has_gameplay_video")
        or inv.get("has_video_artifacts")
    )
    cross = inv.get("cross_artifact_consistency") or {}
    temporal = inv.get("temporal_consistency") or {}
    has_contra = bool(
        cross.get("ambiguities") or temporal.get("temporal_consistency_signals")
    )
    level = int((inv.get("runtime_evidence_level") or {}).get("level") or 0)

    if has_exe and not has_video:
        tags.append("exe_no_video")
    if has_video:
        tags.append("video_modality")
    if has_contra:
        tags.append("contradictory_artifacts")
    if level >= 3:
        tags.append("l3_hints")
    if not has_exe and not has_video:
        tags.append("docx_baseline")
    if has_exe or has_video:
        if not has_contra and level < 3:
            tags.append("weak_runtime_hints")
    if not tags:
        tags.append("docx_baseline")
    return tags


def scan_pilot_pool(submissions: List[Any]) -> Dict[str, Any]:
    """
    Analyze available graded submissions for governance pilot readiness.
    Target cohort: 20–30 balanced mix — not 'best projects'.
    """
    pool: List[Dict[str, Any]] = []
    tag_counts: Dict[str, int] = {}
    batches: Dict[int, Dict[str, Any]] = {}

    for sub in submissions:
        snap = None
        raw = getattr(sub, "grading_snapshot_json", None)
        if raw:
            try:
                snap = json.loads(str(raw))
            except (json.JSONDecodeError, TypeError):
                snap = None
        if not snap:
            continue
        section_a = extract_runtime_evidence_state(snap)
        tags = _categorize_pilot_submission(snap)
        for t in tags:
            tag_counts[t] = tag_counts.get(t, 0) + 1
        bid = getattr(sub, "batch_id", None)
        entry = {
            "submission_id": sub.id,
            "student_name": getattr(sub, "student_name", "") or "",
            "batch_id": bid,
            "tags": tags,
            "section_a": section_a,
        }
        pool.append(entry)
        if bid is not None:
            b = batches.setdefault(bid, {"batch_id": bid, "count": 0, "tags": set()})
            b["count"] += 1
            b["tags"].update(tags)

    batch_list = []
    for b in batches.values():
        batch_list.append({
            "batch_id": b["batch_id"],
            "count": b["count"],
            "tags": sorted(b["tags"]),
        })
    batch_list.sort(key=lambda x: -x["count"])

    target_tags = {
        "docx_baseline": "docx فقط — baseline",
        "exe_no_video": "exe/apk بدون فيديو — authority ambiguity",
        "video_modality": "فيديو/screenshots — modality pressure",
        "contradictory_artifacts": "contradictory — downgrade testing",
        "weak_runtime_hints": "weak evidence — HOLD behaviour",
        "l3_hints": "L3 hints — confusion testing",
    }
    gaps = [k for k in target_tags if tag_counts.get(k, 0) == 0]
    ready = len(pool) >= 20 and len(gaps) <= 2

    return {
        "pool_size": len(pool),
        "target_size": "20-30",
        "ready_for_full_pilot": ready,
        "summary_ar": (
            "الـ pool جاهز لـ pilot كامل (20–30)"
            if ready
            else f"متاح {len(pool)} submission — ارفع batch متوازن أو أكمل الـ mix"
        ),
        "tag_counts": tag_counts,
        "tag_labels_ar": target_tags,
        "coverage_gaps": gaps,
        "recommended_batch_id": batch_list[0]["batch_id"] if batch_list else None,
        "batches": batch_list,
        "submissions": pool,
        "workshop_mode_ar": "authority-boundary observation — ليس grading workshop",
        "golden_signals_ar": [
            "replay not opened → provenance ignored",
            "reviewer says game verified → authority inflation",
            "video overrides contradictions → modality dominance",
            "downgrade rejected → governance instability",
            "HOLD unused → escalation pressure",
            "trust drops → institutional fragility",
        ],
    }


def synthesize_cohort_governance_report(
    *,
    batch_id: int,
    snapshots: List[Dict[str, Any]],
    submission_meta: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Institutional governance stability report — not AI accuracy report.
    Merges automated cohort metrics + manual observations + incidents.
    """
    from app.governance_drift_monitor import analyze_cohort_governance_metrics

    cohort_id = f"batch_{batch_id}"
    automated = analyze_cohort_governance_metrics(snapshots, cohort_id=cohort_id)
    observations = load_observations(batch_id=batch_id)
    incidents = load_incidents(batch_id=batch_id)

    # Replay usage (manual Section B)
    replay_opened = sum(
        1 for o in observations
        if (o.get("section_b_reviewer_behaviour") or {}).get("replay_opened") is True
    )
    obs_n = len(observations) or 1
    l3_confusion = sum(
        1 for o in observations
        if (o.get("section_b_reviewer_behaviour") or {}).get("l3_interpreted_as_verification") is True
    )
    downgrade_accepted = sum(
        1 for o in observations
        if (o.get("section_b_reviewer_behaviour") or {}).get("downgrade_accepted") is True
    )
    authority_override = sum(
        1 for o in observations
        if (o.get("section_b_reviewer_behaviour") or {}).get("authority_boundary_overridden") is True
    )
    hold_applied = sum(
        1 for o in observations
        if (o.get("section_b_reviewer_behaviour") or {}).get("hold_applied") is True
    )

    trust_conf = [
        float((o.get("section_d_trust_signals") or {}).get("reviewer_confidence"))
        for o in observations
        if (o.get("section_d_trust_signals") or {}).get("reviewer_confidence") is not None
    ]
    trust_ret = [
        float((o.get("section_d_trust_signals") or {}).get("trust_retained_after_disagreement"))
        for o in observations
        if (o.get("section_d_trust_signals") or {}).get("trust_retained_after_disagreement") is not None
    ]
    ambig = [
        float((o.get("section_d_trust_signals") or {}).get("ambiguity_understandable"))
        for o in observations
        if (o.get("section_d_trust_signals") or {}).get("ambiguity_understandable") is not None
    ]

    manual_gfm_counts: Dict[str, int] = {}
    for o in observations:
        for ev in o.get("section_c_governance_events") or []:
            key = ev.get("event") or ev.get("failure_mode_id") or "UNKNOWN"
            manual_gfm_counts[key] = manual_gfm_counts.get(key, 0) + 1
    for inc in incidents:
        mid = inc.get("failure_mode_id") or "UNKNOWN"
        manual_gfm_counts[mid] = manual_gfm_counts.get(mid, 0) + 1

    top_manual = sorted(manual_gfm_counts.items(), key=lambda x: -x[1])[:8]

    metrics = automated.get("metrics") or {}
    l3_confusion_rate = round(l3_confusion / obs_n, 3) if observations else metrics.get("l3_verification_confusion_rate")
    replay_consultation_rate = round(replay_opened / obs_n, 3) if observations else None

    # Pilot gate criteria
    gates = {
        "l3_confusion_low": (l3_confusion_rate or 0) == 0,
        "replay_used": replay_consultation_rate is None or replay_consultation_rate >= 0.5,
        "no_s5_silent_drift": automated.get("cohort_max_severity") != "S5"
            or automated.get("export_review_required_count", 0) > 0,
        "observations_recorded": len(observations) >= max(1, min(5, len(snapshots) // 4)),
        "trust_stable": _avg(trust_ret) is None or _avg(trust_ret) >= 3.0,
    }
    pilot_pass = all(gates.values()) and len(snapshots) >= 1

    try:
        from app.governance_mitigation_memory import analyze_mitigation_effectiveness

        mitigation = analyze_mitigation_effectiveness(cohort_id=cohort_id, batch_id=batch_id)
    except Exception:
        mitigation = {}

    epistemic_evidence = synthesize_epistemic_behavioural_evidence(
        observations, batch_id=batch_id
    )

    return {
        "report_type": "institutional_governance_stability_report",
        "not": "AI accuracy report",
        "worksheet_version": WORKSHEET_VERSION,
        "cohort_id": cohort_id,
        "batch_id": batch_id,
        "submission_count": len(snapshots),
        "observations_count": len(observations),
        "incidents_count": len(incidents),
        "purpose_ar": (
            "تقرير استقرار الحوكمة المؤسسية — "
            "سلوك المراجعين + drift + mitigation — وليس دقة AI."
        ),
        "automated_cohort_metrics": metrics,
        "human_observation_metrics": {
            "replay_consultation_rate": replay_consultation_rate,
            "l3_verification_confusion_rate_manual": l3_confusion_rate,
            "downgrade_acceptance_rate": round(downgrade_accepted / obs_n, 3) if observations else None,
            "authority_boundary_override_rate": round(authority_override / obs_n, 3) if observations else None,
            "hold_utilization_rate": round(hold_applied / obs_n, 3) if observations else None,
            "avg_reviewer_confidence": _avg(trust_conf),
            "avg_trust_retained": _avg(trust_ret),
            "avg_ambiguity_understandable": _avg(ambig),
        },
        "top_gfms_manual_and_incidents": [{"mode_id": m, "count": c} for m, c in top_manual],
        "automated_failure_taxonomy": automated.get("failure_taxonomy"),
        "export_gate_interventions": {
            "export_review_required_count": automated.get("export_review_required_count", 0),
            "cohort_max_severity": automated.get("cohort_max_severity"),
        },
        "replay_usage_patterns": {
            "replay_presence_rate_automated": metrics.get("replay_presence_rate"),
            "replay_consultation_rate_manual": replay_consultation_rate,
            "replay_opened_count": replay_opened,
            "observations_with_replay_no": sum(
                1 for o in observations
                if (o.get("section_b_reviewer_behaviour") or {}).get("replay_opened") is False
            ),
        },
        "l3_confusion_map": {
            "automated_rate": metrics.get("l3_verification_confusion_rate"),
            "manual_confusion_count": l3_confusion,
            "manual_observations": len(observations),
        },
        "mitigation_effectiveness": mitigation,
        "epistemic_behavioural_evidence": epistemic_evidence,
        "pilot_gate": {
            "criteria": gates,
            "ready_for_l4_rfc": pilot_pass,
            "summary_ar": (
                "جاهز لـ RFC L4 sandbox"
                if pilot_pass
                else "Pilot غير مكتمل — لا تبدأ L4 sandbox بعد"
            ),
        },
        "submissions": submission_meta or [],
        "next_steps_ar": [
            "راجع top GFMs في ورشة follow-up",
            "سجّل mitigation outcomes للحالات المتكررة",
            "لا tuning prompts ولا sandbox قبل اجتياز pilot gate",
        ],
    }
