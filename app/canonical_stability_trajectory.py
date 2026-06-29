"""
Canonical Stability Trajectory — governance trajectory interpretation over time.

Time-series snapshots, stability transition events, and freeze-epoch-relative
readings — not dashboard analytics alone.
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.canonical_stability_metrics import (
    METRICS_VERSION,
    compute_canonical_stability_metrics,
)

HISTORY_DIR = Path("app/calibration")
HISTORY_FILE = "canonical_stability_history.jsonl"

# Freeze epoch registry — metrics read relative to active governance epoch
FREEZE_EPOCHS: Dict[str, Dict[str, Any]] = {
    "epoch_1": {
        "freeze_id": "GOVERNANCE_FREEZE_v1",
        "status": "active",
        "since": "2026-05-22",
        "label_ar": "الخط الأساسي — L0–L3 frozen",
    },
    "epoch_2": {
        "freeze_id": "GOVERNANCE_FREEZE_v2",
        "status": "planned",
        "since": None,
        "label_ar": "RFC مستقبلي — post-pilot",
    },
    "epoch_3": {
        "freeze_id": "post_L4_sandbox",
        "status": "planned",
        "since": None,
        "label_ar": "ما بعد L4 sandbox RFC",
    },
}

ACTIVE_FREEZE_EPOCH = "epoch_1"

BAND_RANK = {"green": 0, "amber": 1, "red": 2, "unknown": -1}

TRANSITION_MEANINGS: Dict[str, Dict[str, str]] = {
    "red_to_amber": {
        "event": "mitigation_working",
        "meaning_ar": "تحسّن جزئي — mitigation قد يعمل",
    },
    "amber_to_green": {
        "event": "governance_stabilizing",
        "meaning_ar": "استقرار حوكمي — trajectory إيجابية",
    },
    "green_to_amber": {
        "event": "stability_softening",
        "meaning_ar": "تراجع طفيف — راقب replay وoverride",
    },
    "green_to_red": {
        "event": "new_drift_introduced",
        "meaning_ar": "خطر — drift جديد داخل نفس freeze epoch",
    },
    "amber_to_red": {
        "event": "governance_degrading",
        "meaning_ar": "تدهور — canonical authority under pressure",
    },
    "red_to_green": {
        "event": "recovery_complete",
        "meaning_ar": "تعافٍ كامل — rare; verify not masking variance",
    },
    "replay_reuse_collapse": {
        "event": "replay_reuse_collapse",
        "meaning_ar": "انهيار replay reuse — provenance abandonment محتمل",
    },
    "override_spike": {
        "event": "override_spike",
        "meaning_ar": "ارتفاع override — canonical distrust أو reviewer pressure",
    },
    "hash_divergence_spike": {
        "event": "hash_divergence_spike",
        "meaning_ar": "epistemic reproducibility heartbeat — identical evidence diverged",
    },
}


def _history_path() -> Path:
    HISTORY_DIR.mkdir(parents=True, exist_ok=True)
    return HISTORY_DIR / HISTORY_FILE


def active_freeze_context() -> Dict[str, Any]:
    epoch = FREEZE_EPOCHS.get(ACTIVE_FREEZE_EPOCH, {})
    return {
        "freeze_epoch": ACTIVE_FREEZE_EPOCH,
        "freeze_id": epoch.get("freeze_id", "GOVERNANCE_FREEZE_v1"),
        "epoch_status": epoch.get("status", "active"),
        "epoch_label_ar": epoch.get("label_ar", ""),
        "epochs_registry": FREEZE_EPOCHS,
    }


def enrich_with_freeze_epoch(report: Dict[str, Any]) -> Dict[str, Any]:
    ctx = active_freeze_context()
    out = dict(report)
    out["freeze_epoch"] = ctx
    out["interpretation_scope_ar"] = (
        f"المقاييس تُقرأ relative to {ctx['freeze_id']} ({ctx['freeze_epoch']}) — "
        "بعض drift طبيعي بعد freeze evolution؛ drift داخل نفس epoch = dangerous."
    )
    return out


def record_stability_snapshot(report: Dict[str, Any]) -> Dict[str, Any]:
    """Append one stability reading to institutional time-series (JSONL)."""
    enriched = enrich_with_freeze_epoch(report)
    row = {
        "recorded_at": datetime.datetime.utcnow().isoformat() + "Z",
        "metrics_version": METRICS_VERSION,
        **{k: enriched.get(k) for k in (
            "scope", "submission_count", "overall_stability",
            "metrics", "health_bands", "counts", "freeze_epoch",
        ) if k in enriched},
    }
    path = _history_path()
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def load_stability_history(
    *,
    assignment_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    freeze_epoch: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    path = _history_path()
    if not path.exists():
        return []
    rows: List[Dict[str, Any]] = []
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            scope = row.get("scope") or {}
            if assignment_id is not None and scope.get("assignment_id") != assignment_id:
                continue
            if batch_id is not None and scope.get("batch_id") != batch_id:
                continue
            fe = (row.get("freeze_epoch") or {}).get("freeze_epoch")
            if freeze_epoch and fe != freeze_epoch:
                continue
            rows.append(row)
    return rows[-limit:]


def detect_stability_transitions(
    previous: Optional[Dict[str, Any]],
    current: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """Governance trajectory transition events — more important than raw numbers."""
    if not previous:
        return [{
            "event": "baseline_recorded",
            "meaning_ar": "أول قراءة stability — baseline للم trajectory",
            "severity": "info",
        }]

    events: List[Dict[str, Any]] = []
    prev_bands = previous.get("health_bands") or {}
    curr_bands = current.get("health_bands") or {}
    prev_metrics = previous.get("metrics") or {}
    curr_metrics = current.get("metrics") or {}

    for key, curr_h in curr_bands.items():
        prev_h = prev_bands.get(key) or {}
        pb = prev_h.get("band", "unknown")
        cb = curr_h.get("band", "unknown")
        if pb == cb or pb == "unknown" or cb == "unknown":
            continue
        transition_key = f"{pb}_to_{cb}"
        meta = TRANSITION_MEANINGS.get(transition_key, {})
        events.append({
            "event": meta.get("event", transition_key),
            "transition": transition_key,
            "metric": key,
            "from_band": pb,
            "to_band": cb,
            "from_value": prev_metrics.get(key),
            "to_value": curr_metrics.get(key),
            "meaning_ar": meta.get("meaning_ar", f"{key}: {pb} → {cb}"),
            "severity": "high" if cb == "red" and pb in ("green", "amber") else "medium",
        })

    prev_replay = float(prev_metrics.get("replay_reuse_rate") or 0)
    curr_replay = float(curr_metrics.get("replay_reuse_rate") or 0)
    if prev_replay >= 0.15 and curr_replay <= 0.05:
        meta = TRANSITION_MEANINGS["replay_reuse_collapse"]
        events.append({
            "event": meta["event"],
            "metric": "replay_reuse_rate",
            "from_value": prev_replay,
            "to_value": curr_replay,
            "meaning_ar": meta["meaning_ar"],
            "severity": "high",
            "institutional_trust_proxy": True,
        })

    prev_override = float(prev_metrics.get("override_after_canonical_rate") or 0)
    curr_override = float(curr_metrics.get("override_after_canonical_rate") or 0)
    if curr_override - prev_override >= 0.15:
        meta = TRANSITION_MEANINGS["override_spike"]
        events.append({
            "event": meta["event"],
            "metric": "override_after_canonical_rate",
            "from_value": prev_override,
            "to_value": curr_override,
            "meaning_ar": meta["meaning_ar"],
            "severity": "high",
        })

    prev_hash = float(prev_metrics.get("evidence_hash_divergence_rate") or 0)
    curr_hash = float(curr_metrics.get("evidence_hash_divergence_rate") or 0)
    if curr_hash - prev_hash >= 0.1:
        meta = TRANSITION_MEANINGS["hash_divergence_spike"]
        events.append({
            "event": meta["event"],
            "metric": "evidence_hash_divergence_rate",
            "from_value": prev_hash,
            "to_value": curr_hash,
            "meaning_ar": meta["meaning_ar"],
            "severity": "critical",
            "epistemic_reproducibility_heartbeat": True,
        })

    prev_overall = previous.get("overall_stability")
    curr_overall = current.get("overall_stability")
    if prev_overall and curr_overall and prev_overall != curr_overall:
        tk = f"{prev_overall}_to_{curr_overall}"
        meta = TRANSITION_MEANINGS.get(tk, {})
        events.append({
            "event": meta.get("event", f"overall_{tk}"),
            "transition": tk,
            "metric": "overall_stability",
            "from_band": prev_overall,
            "to_band": curr_overall,
            "meaning_ar": meta.get("meaning_ar", f"overall stability: {prev_overall} → {curr_overall}"),
            "severity": "high" if curr_overall == "red" else "medium",
        })

    return events


def build_governance_trajectory_report(
    db: Any,
    *,
    assignment_id: Optional[int] = None,
    batch_id: Optional[int] = None,
    record_snapshot: bool = False,
) -> Dict[str, Any]:
    """
    Institutional stability trajectory — current reading + history + transitions.
    """
    if batch_id is not None and assignment_id is None:
        from app.models import BatchGrading

        batch = db.query(BatchGrading).filter(BatchGrading.id == batch_id).first()
        if batch:
            assignment_id = batch.assignment_id

    current = enrich_with_freeze_epoch(
        compute_canonical_stability_metrics(
            db, assignment_id=assignment_id, batch_id=batch_id
        )
    )

    history = load_stability_history(
        assignment_id=assignment_id,
        batch_id=None,
        freeze_epoch=ACTIVE_FREEZE_EPOCH,
    )
    previous = history[-1] if history else None
    transitions = detect_stability_transitions(previous, current)

    if record_snapshot:
        record_stability_snapshot(current)

    trajectory_interpretation: List[str] = []
    for ev in transitions:
        trajectory_interpretation.append(ev.get("meaning_ar", ev.get("event", "")))

    if not history:
        trajectory_interpretation.append(
            "لا baseline سابق — سجّل readings بعد كل batch لبناء governance trajectory."
        )
    elif current.get("overall_stability") == "green" and not any(
        e.get("severity") in ("high", "critical") for e in transitions
    ):
        trajectory_interpretation.append(
            "trajectory مستقرة داخل freeze epoch الحالي — استمر replay-first policy."
        )

    return {
        "report_type": "governance_trajectory_report",
        "not": "dashboard analytics",
        "layer": "institutional_stability_observability",
        "purpose_ar": (
            "تفسير trajectory الحوكمة — transitions أهم من الأرقام — "
            "relative to freeze epoch."
        ),
        "current": current,
        "freeze_epoch": current.get("freeze_epoch"),
        "history_points": len(history),
        "history": history[-10:],
        "stability_transitions": transitions,
        "trajectory_interpretation_ar": trajectory_interpretation,
        "epistemic_reproducibility_heartbeat": {
            "metric": "evidence_hash_divergence_rate",
            "current": (current.get("metrics") or {}).get("evidence_hash_divergence_rate"),
            "band": (current.get("health_bands") or {}).get("evidence_hash_divergence_rate", {}).get("band"),
            "question_ar": "هل identical institutional evidence يبقى stable عبر الزمن؟",
        },
        "institutional_trust_proxy": {
            "metric": "replay_reuse_rate",
            "current": (current.get("metrics") or {}).get("replay_reuse_rate"),
            "band": (current.get("health_bands") or {}).get("replay_reuse_rate", {}).get("band"),
            "note_ar": "انخفاض replay قد يعني provenance abandonment أو canonical distrust.",
        },
    }
