"""
Governance Epoch Narrative — institutional memory per freeze epoch.

Synthesizes trajectory, GFMs, mitigation, and replay trust into an
interpretable epoch story — not dashboard analytics.
"""
from __future__ import annotations

import datetime
from collections import Counter
from typing import Any, Dict, List, Optional

from app.canonical_stability_trajectory import (
    ACTIVE_FREEZE_EPOCH,
    FREEZE_EPOCHS,
    load_stability_history,
    detect_stability_transitions,
)
from app.governance_failure_taxonomy import FAILURE_MODES, TAXONOMY_ID

NARRATIVE_VERSION = "governance_epoch_narrative_v1"
RFC_REVIEW_VERSION = "governance_epoch_review_rfc_v1"

# Epoch-specific institutional themes (enriched by live data)
EPOCH_THEMES: Dict[str, List[Dict[str, str]]] = {
    "epoch_1": [
        {
            "theme": "L0-L3_stabilized",
            "meaning_ar": "دلالات L0–L3 استقرت — advisory semantics نضجت",
        },
        {
            "theme": "no_L4_authority",
            "meaning_ar": "لا L4 authority تلقائية — runtime bounded",
        },
        {
            "theme": "canonical_drift_discovered",
            "meaning_ar": "اكتُشف canonical drift — reproducibility governance gap",
        },
        {
            "theme": "supersession_policy",
            "meaning_ar": "institutional supersession — variance محفوظة غير authoritative",
        },
    ],
}


def _aggregate_history_metrics(history: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not history:
        return {"readings": 0}
    metrics_keys = list((history[-1].get("metrics") or {}).keys())
    series: Dict[str, List[float]] = {k: [] for k in metrics_keys}
    overall_bands: List[str] = []
    for row in history:
        overall_bands.append(str(row.get("overall_stability") or "unknown"))
        for k in metrics_keys:
            v = (row.get("metrics") or {}).get(k)
            if v is not None:
                series[k].append(float(v))

    def _trend(vals: List[float]) -> str:
        if len(vals) < 2:
            return "insufficient_data"
        delta = vals[-1] - vals[0]
        if abs(delta) < 0.02:
            return "stable"
        return "improving" if delta > 0 else "degrading"

    replay = series.get("replay_reuse_rate") or []
    drift = series.get("canonical_drift_rate") or []
    hash_div = series.get("evidence_hash_divergence_rate") or []
    override = series.get("override_after_canonical_rate") or []
    clean = series.get("governance_clean_ratio") or []

    return {
        "readings": len(history),
        "first_recorded": history[0].get("recorded_at"),
        "last_recorded": history[-1].get("recorded_at"),
        "overall_stability_first": overall_bands[0] if overall_bands else None,
        "overall_stability_last": overall_bands[-1] if overall_bands else None,
        "replay_reuse_trend": _trend(replay) if replay else "insufficient_data",
        "replay_reuse_last": replay[-1] if replay else None,
        "canonical_drift_trend": _trend([ -v for v in drift]) if drift else "insufficient_data",
        "hash_divergence_trend": _trend([ -v for v in hash_div]) if hash_div else "insufficient_data",
        "override_trend": _trend(override) if override else "insufficient_data",
        "governance_clean_trend": _trend(clean) if clean else "insufficient_data",
    }


def _collect_transition_events(history: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    events: List[Dict[str, Any]] = []
    for i in range(1, len(history)):
        events.extend(detect_stability_transitions(history[i - 1], history[i]))
    return events


def _replay_trust_interpretation(agg: Dict[str, Any]) -> Dict[str, Any]:
    replay_last = agg.get("replay_reuse_last")
    replay_trend = agg.get("replay_reuse_trend")
    override_trend = agg.get("override_trend")

    state = "unknown"
    interpretation_ar = "بيانات replay trust غير كافية بعد."

    if replay_last is not None:
        if replay_last >= 0.2 and override_trend != "degrading":
            state = "canonical_trusted"
            interpretation_ar = (
                "replay reuse مرتفع — canonical trusted؛ provenance adoption جيد."
            )
        elif replay_last <= 0.05:
            state = "provenance_abandonment_risk"
            interpretation_ar = (
                "replay reuse منهار — provenance abandonment أو canonical distrust محتمل."
            )
        elif replay_trend == "improving":
            state = "governance_stabilizing"
            interpretation_ar = "replay reuse يرتفع — governance stabilization trajectory."
        elif override_trend == "degrading":
            state = "canonical_legitimacy_pressure"
            interpretation_ar = (
                "overrides ترتفع — canonical legitimacy weakening؛ راجع reviewer training."
            )
        else:
            state = "mixed"
            interpretation_ar = "replay trust mixed — راقب transitions."

    return {
        "state": state,
        "interpretation_ar": interpretation_ar,
        "replay_reuse_last": replay_last,
        "replay_trend": replay_trend,
        "override_trend": override_trend,
    }


def build_epoch_narrative(
    db: Any,
    *,
    epoch_id: str = ACTIVE_FREEZE_EPOCH,
    assignment_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Institutional narrative for one governance freeze epoch.
    """
    epoch_meta = FREEZE_EPOCHS.get(epoch_id)
    if not epoch_meta:
        return {"error": f"Unknown epoch: {epoch_id}"}

    history = load_stability_history(
        assignment_id=assignment_id,
        freeze_epoch=epoch_id,
        limit=200,
    )
    agg = _aggregate_history_metrics(history)
    transitions = _collect_transition_events(history)
    transition_counts = Counter(e.get("event") for e in transitions)

    gfm_signals: Dict[str, int] = {}
    for ev in transitions:
        if ev.get("epistemic_reproducibility_heartbeat"):
            gfm_signals["GFM_CANONICAL_DRIFT"] = gfm_signals.get("GFM_CANONICAL_DRIFT", 0) + 1
        if ev.get("institutional_trust_proxy"):
            gfm_signals["GFM_TRUST_EROSION"] = gfm_signals.get("GFM_TRUST_EROSION", 0) + 1

    try:
        from app.governance_mitigation_memory import analyze_mitigation_effectiveness

        mitigation = analyze_mitigation_effectiveness()
    except Exception:
        mitigation = {}

    replay_trust = _replay_trust_interpretation(agg)
    themes = list(EPOCH_THEMES.get(epoch_id, []))

    narrative_bullets: List[str] = []
    for t in themes:
        narrative_bullets.append(f"• {t['meaning_ar']}")

    if agg.get("readings", 0) > 0:
        narrative_bullets.append(
            f"• {agg['readings']} stability reading(s) داخل {epoch_id} "
            f"({agg.get('overall_stability_first')} → {agg.get('overall_stability_last')})"
        )
    if transition_counts.get("hash_divergence_spike"):
        narrative_bullets.append(
            "• hash_divergence_spike — institutional heartbeat anomaly (reproducibility risk)"
        )
    if transition_counts.get("replay_reuse_collapse"):
        narrative_bullets.append("• replay_reuse_collapse — provenance abandonment signal")
    if transition_counts.get("governance_stabilizing"):
        narrative_bullets.append("• governance_stabilizing — mitigation trajectory positive")

    narrative_bullets.append(f"• replay trust: {replay_trust['interpretation_ar']}")

    return {
        "report_type": "governance_epoch_narrative",
        "narrative_version": NARRATIVE_VERSION,
        "layer": "institutional_governance_memory",
        "epoch_id": epoch_id,
        "freeze_id": epoch_meta.get("freeze_id"),
        "epoch_status": epoch_meta.get("status"),
        "epoch_since": epoch_meta.get("since"),
        "epoch_label_ar": epoch_meta.get("label_ar"),
        "scope": {"assignment_id": assignment_id},
        "purpose_ar": (
            "سرد مؤسسي للـ epoch — institutional governance memory — "
            "وليس dashboard analytics."
        ),
        "characteristics": themes,
        "stability_summary": agg,
        "replay_trust_state": replay_trust,
        "transition_event_counts": dict(transition_counts),
        "notable_transitions": transitions[-15:],
        "gfm_signals_in_epoch": gfm_signals,
        "mitigation_summary": {
            "total_records": mitigation.get("total_records", 0),
            "effective_rate": mitigation.get("overall_effectiveness_rate"),
            "top_modes": (mitigation.get("by_failure_mode") or [])[:5],
        },
        "narrative_ar": narrative_bullets,
        "institutional_memory_note_ar": (
            "هذا السرد يُستخدم في calibration reviews وepoch RFC — "
            "drift داخل epoch = خطر؛ drift بعد evolution = expected."
        ),
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }


def build_epoch_review_rfc_package(
    db: Any,
    *,
    target_epoch_id: str,
    current_epoch_id: str = ACTIVE_FREEZE_EPOCH,
    assignment_id: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Pre-RFC review package — epoch transition must be institutionally justified.
    """
    current_narrative = build_epoch_narrative(
        db, epoch_id=current_epoch_id, assignment_id=assignment_id
    )
    target_meta = FREEZE_EPOCHS.get(target_epoch_id, {})

    history = load_stability_history(
        assignment_id=assignment_id,
        freeze_epoch=current_epoch_id,
        limit=200,
    )
    agg = _aggregate_history_metrics(history)
    transitions = _collect_transition_events(history)

    unresolved_gfms: List[Dict[str, Any]] = []
    for gfm_id, count in (current_narrative.get("gfm_signals_in_epoch") or {}).items():
        mode = FAILURE_MODES.get(gfm_id, {})
        unresolved_gfms.append({
            "failure_mode_id": gfm_id,
            "label_ar": mode.get("label_ar"),
            "signal_count": count,
            "default_severity": mode.get("default_severity"),
        })

    unresolved_gfms.sort(key=lambda x: -x.get("signal_count", 0))

    gates = {
        "canonical_drift_under_control": agg.get("canonical_drift_trend") != "degrading",
        "hash_divergence_not_spiking": not any(
            e.get("event") == "hash_divergence_spike" for e in transitions[-5:]
        ),
        "replay_trust_not_collapsed": (
            current_narrative.get("replay_trust_state") or {}
        ).get("state") != "provenance_abandonment_risk",
        "mitigation_documented": (
            current_narrative.get("mitigation_summary") or {}
        ).get("total_records", 0) > 0,
        "narrative_recorded": agg.get("readings", 0) >= 1,
    }
    rfc_ready = all(gates.values())

    return {
        "report_type": "governance_epoch_review_rfc_package",
        "rfc_version": RFC_REVIEW_VERSION,
        "taxonomy_id": TAXONOMY_ID,
        "purpose_ar": (
            "حزمة مراجعة RFC قبل epoch transition — "
            "epoch transition justified institutionally وليس «قمنا بتحديث النظام»."
        ),
        "current_epoch": {
            "epoch_id": current_epoch_id,
            "freeze_id": FREEZE_EPOCHS.get(current_epoch_id, {}).get("freeze_id"),
            "narrative": current_narrative,
        },
        "proposed_epoch": {
            "epoch_id": target_epoch_id,
            "freeze_id": target_meta.get("freeze_id"),
            "status": target_meta.get("status"),
            "label_ar": target_meta.get("label_ar"),
        },
        "drift_summary": {
            "stability_readings": agg.get("readings", 0),
            "overall_trajectory": f"{agg.get('overall_stability_first')} → {agg.get('overall_stability_last')}",
            "hash_divergence_trend": agg.get("hash_divergence_trend"),
            "canonical_drift_trend": agg.get("canonical_drift_trend"),
        },
        "stability_trajectory": {
            "transition_events": len(transitions),
            "recent": transitions[-10:],
        },
        "unresolved_gfms": unresolved_gfms,
        "replay_trust_state": current_narrative.get("replay_trust_state"),
        "mitigation_effectiveness": current_narrative.get("mitigation_summary"),
        "rfc_gate_criteria": gates,
        "rfc_transition_ready": rfc_ready,
        "rfc_summary_ar": (
            "جاهز لـ epoch transition RFC"
            if rfc_ready
            else "غير جاهز — أكمل drift mitigation وreplay trust stabilization أولاً"
        ),
        "baseline_policy_ar": (
            "عند transition: reset baselines within new epoch — "
            "cross-epoch history preserved (no global erase)."
        ),
        "required_before_transition_ar": [
            "drift summary reviewed",
            "stability trajectory documented",
            "unresolved GFMs addressed or accepted",
            "replay trust state stable",
            "mitigation effectiveness recorded",
            "epoch narrative archived",
        ],
        "generated_at": datetime.datetime.utcnow().isoformat() + "Z",
    }
